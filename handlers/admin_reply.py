from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, ForceReply, Message

from callbacks import ReplyOrderCallback
from config import Config
from database import Database
from keyboards.conversation import client_reply_keyboard
from utils.formatting import h


router = Router(name="admin_reply")
fallback_router = Router(name="admin_reply_fallback")
logger = logging.getLogger(__name__)


async def _answer_callback(
    callback: CallbackQuery,
    text: str,
    *,
    show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramAPIError as exc:
        logger.info("Could not acknowledge an expired callback query: %s", exc)


def _client_label(order: object) -> str:
    first_name = order["first_name"] or ""
    last_name = order["last_name"] or ""
    return " ".join(part for part in (first_name, last_name) if part).strip() or "Не указано"


@router.callback_query(ReplyOrderCallback.filter())
async def create_admin_reply_prompt(
    callback: CallbackQuery,
    callback_data: ReplyOrderCallback,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message) or callback.message.chat.id != config.admin_chat_id:
        await _answer_callback(callback, "Действие недоступно.", show_alert=True)
        return
    order = database.get_order(callback_data.order_id)
    if order is None:
        await _answer_callback(callback, "Заявка не найдена.", show_alert=True)
        return
    username = f"@{h(order['username'])}" if order["username"] else "отсутствует"
    prompt = await bot.send_message(
        config.admin_chat_id,
        f"<b>💬 Ответ на заявку #{order['id']}</b>\n\n"
        f"Клиент: {h(_client_label(order))}\n"
        f"Username: {username}\n"
        f"Telegram ID: <code>{order['telegram_user_id']}</code>\n\n"
        "Введите ответ клиенту:",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder="Введите ответ клиенту",
        ),
    )
    database.save_admin_reply_prompt(
        config.admin_chat_id,
        prompt.message_id,
        int(order["id"]),
        created_at=datetime.now(config.timezone).isoformat(timespec="seconds"),
    )
    await _answer_callback(callback, "Создано сообщение для ответа.")


@router.message(F.reply_to_message)
async def deliver_admin_reply(
    message: Message,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    if message.chat.id != config.admin_chat_id or not message.reply_to_message:
        raise SkipHandler
    order = database.get_order_for_admin_prompt(
        config.admin_chat_id,
        message.reply_to_message.message_id,
    )
    if order is None:
        order = database.get_order_for_conversation_message(
            config.admin_chat_id,
            message.reply_to_message.message_id,
        )
    if order is None:
        await message.answer(
            "⚠️ Не удалось определить заявку. Нажмите «Ответить клиенту» "
            "в нужной заявке и отправьте сообщение через открывшийся ответ."
        )
        return
    reply_text = (
        getattr(message, "text", None) or getattr(message, "caption", None) or ""
    ).strip()
    is_media = bool(
        getattr(message, "photo", None) or getattr(message, "document", None)
    )
    if not reply_text and not is_media:
        await message.answer(
            "Поддерживаются текст, фотография и документ с необязательной подписью."
        )
        return
    client_chat_id = int(order["telegram_chat_id"] or order["telegram_user_id"])
    header = f"<b>💬 Ответ DES Studio по заявке #{order['id']}</b>"
    text_limit = 700 if is_media else 3500
    safe_reply_text = reply_text[:text_limit]
    if len(reply_text) > text_limit:
        safe_reply_text += "…"
    body = f"\n\n{h(safe_reply_text)}" if safe_reply_text else ""
    try:
        if is_media:
            delivered = await bot.copy_message(
                chat_id=client_chat_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                caption=f"{header}{body}",
                reply_markup=client_reply_keyboard(int(order["id"])),
            )
        else:
            delivered = await bot.send_message(
                client_chat_id,
                f"{header}{body}",
                reply_markup=client_reply_keyboard(int(order["id"])),
            )
    except TelegramAPIError:
        logger.warning(
            "Could not deliver admin reply for order %s to Telegram user %s",
            order["id"],
            order["telegram_user_id"],
            exc_info=True,
        )
        await message.answer(
            f"Не удалось доставить ответ клиенту по заявке #{order['id']}. "
            "Возможно, клиент заблокировал бота."
        )
        return
    delivered_at = datetime.now(config.timezone).isoformat(timespec="seconds")
    database.open_conversation_with_message(
        int(order["id"]),
        client_chat_id,
        delivered.message_id,
        "admin_to_client",
        opened_at=delivered_at,
    )
    await message.answer(f"✅ Ответ по заявке #{order['id']} доставлен клиенту.")


@fallback_router.message()
async def explain_unlinked_admin_message(message: Message, config: Config) -> None:
    if message.chat.id != config.admin_chat_id:
        return
    if message.text and message.text.startswith("/"):
        return
    await message.answer(
        "⚠️ Не удалось определить заявку. Нажмите «Ответить клиенту» "
        "в нужной заявке и отправьте сообщение через открывшийся ответ."
    )
