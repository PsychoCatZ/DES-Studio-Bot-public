from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, ForceReply, Message

from callbacks import ClientReplyOrderCallback, ClientSelectOrderCallback
from config import Config
from database import Database
from keyboards.admin import admin_order_keyboard
from keyboards.conversation import conversation_selection_keyboard
from utils.formatting import h


priority_router = Router(name="conversation_priority")
router = Router(name="conversation")
logger = logging.getLogger(__name__)


async def _answer_callback(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramAPIError as exc:
        logger.info("Could not acknowledge an expired callback query: %s", exc)


def _content(message: Message) -> tuple[str | None, str | None]:
    if message.text:
        return "text", message.text.strip()
    if message.photo:
        return "photo", (message.caption or "").strip() or None
    if message.document:
        return "document", (message.caption or "").strip() or None
    return None, None


def _client_name(order: object) -> str:
    parts = (order["first_name"] or "", order["last_name"] or "")
    return " ".join(part for part in parts if part).strip() or "Не указано"


def _admin_client_message(
    order: object,
    content_type: str,
    content_text: str | None,
    *,
    caption_limit: bool,
) -> str:
    username = f"@{h(order['username'])}" if order["username"] else "отсутствует"
    if content_text:
        limit = 550 if caption_limit else 3000
        content = h(content_text[:limit])
    elif content_type == "photo":
        content = "[Фотография без подписи]"
    else:
        content = "[Документ без подписи]"
    return (
        f"<b>💬 Ответ клиента по заявке #{order['id']}</b>\n\n"
        f"Клиент: {h(_client_name(order))}\n"
        f"Username: {username}\n"
        f"Telegram ID: <code>{order['telegram_user_id']}</code>\n\n"
        f"{content}"
    )


async def _deliver_client_message(
    *,
    order: object,
    source_chat_id: int,
    source_message_id: int,
    content_type: str,
    content_text: str | None,
    bot: Bot,
    database: Database,
    config: Config,
) -> bool:
    try:
        if content_type == "text":
            delivered = await bot.send_message(
                config.admin_chat_id,
                _admin_client_message(
                    order, content_type, content_text, caption_limit=False
                ),
                reply_markup=admin_order_keyboard(int(order["id"])),
            )
        else:
            delivered = await bot.copy_message(
                chat_id=config.admin_chat_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
                caption=_admin_client_message(
                    order, content_type, content_text, caption_limit=True
                ),
                reply_markup=admin_order_keyboard(int(order["id"])),
            )
    except TelegramAPIError:
        logger.warning(
            "Could not deliver client message for order %s to admin chat",
            order["id"],
            exc_info=True,
        )
        return False

    database.save_conversation_message(
        int(order["id"]),
        config.admin_chat_id,
        delivered.message_id,
        "client_to_admin",
        created_at=datetime.now(config.timezone).isoformat(timespec="seconds"),
    )
    return True


async def _confirm_client_delivery(bot: Bot, chat_id: int, order_id: int) -> None:
    await bot.send_message(
        chat_id,
        f"✅ Сообщение по заявке #{order_id} отправлено DES Studio.",
    )


@priority_router.callback_query(ClientReplyOrderCallback.filter())
async def create_client_reply_prompt(
    callback: CallbackQuery,
    callback_data: ClientReplyOrderCallback,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await _answer_callback(callback, "Не удалось открыть ответ.", show_alert=True)
        return
    order = database.get_open_order_for_client(
        callback_data.order_id,
        callback.from_user.id,
    )
    if order is None:
        await _answer_callback(
            callback, "Переписка по этой заявке недоступна.", show_alert=True
        )
        return
    prompt = await bot.send_message(
        callback.message.chat.id,
        f"<b>💬 Ответ по заявке #{order['id']}</b>\n\nВведите сообщение:",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder=f"Ответ по заявке #{order['id']}",
        ),
    )
    database.save_conversation_message(
        int(order["id"]),
        callback.message.chat.id,
        prompt.message_id,
        "client_reply_prompt",
        created_at=datetime.now(config.timezone).isoformat(timespec="seconds"),
    )
    await _answer_callback(callback, "Открыто поле ответа.")


@priority_router.callback_query(ClientSelectOrderCallback.filter())
async def select_client_conversation(
    callback: CallbackQuery,
    callback_data: ClientSelectOrderCallback,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await _answer_callback(callback, "Не удалось выбрать заявку.", show_alert=True)
        return
    pending = database.get_pending_conversation_message(
        callback.message.chat.id,
        callback_data.client_message_id,
    )
    order = database.get_open_order_for_client(
        callback_data.order_id,
        callback.from_user.id,
    )
    if (
        pending is None
        or order is None
        or int(pending["telegram_user_id"]) != callback.from_user.id
    ):
        await _answer_callback(
            callback, "Сообщение или заявка уже недоступны.", show_alert=True
        )
        return
    delivered = await _deliver_client_message(
        order=order,
        source_chat_id=int(pending["telegram_chat_id"]),
        source_message_id=int(pending["telegram_message_id"]),
        content_type=str(pending["content_type"]),
        content_text=pending["content_text"],
        bot=bot,
        database=database,
        config=config,
    )
    if not delivered:
        await _answer_callback(
            callback,
            "Не удалось отправить сообщение. Попробуйте ещё раз.",
            show_alert=True,
        )
        return
    database.delete_pending_conversation_message(
        int(pending["telegram_chat_id"]),
        int(pending["telegram_message_id"]),
    )
    await callback.message.edit_text(
        f"✅ Сообщение отправлено по заявке #{order['id']}."
    )
    await _answer_callback(callback)


async def _route_client_message(
    message: Message,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    if message.chat.id == config.admin_chat_id:
        raise SkipHandler
    if message.from_user is None:
        return
    if message.text and message.text.startswith("/"):
        return

    content_type, content_text = _content(message)
    if content_type is None:
        await message.answer(
            "Поддерживаются текстовые сообщения, фотографии и документы."
        )
        return

    order = None
    if message.reply_to_message:
        candidate = database.get_order_for_conversation_message(
            message.chat.id,
            message.reply_to_message.message_id,
        )
        if candidate is not None:
            order = database.get_open_order_for_client(
                int(candidate["id"]),
                message.from_user.id,
            )

    open_orders = database.get_open_orders_for_client(message.from_user.id)
    if order is None and len(open_orders) == 1:
        order = open_orders[0]

    if order is not None:
        delivered = await _deliver_client_message(
            order=order,
            source_chat_id=message.chat.id,
            source_message_id=message.message_id,
            content_type=content_type,
            content_text=content_text,
            bot=bot,
            database=database,
            config=config,
        )
        if delivered:
            await _confirm_client_delivery(bot, message.chat.id, int(order["id"]))
        else:
            await message.answer("Не удалось отправить сообщение. Попробуйте ещё раз.")
        return

    if not open_orders:
        if database.client_has_orders(message.from_user.id):
            await message.answer(
                "✅ Заявка уже отправлена. Возможность ответить по ней появится "
                "после сообщения DES Studio."
            )
        else:
            await message.answer(
                "Чтобы связаться с DES Studio, сначала оформите заявку через главное меню."
            )
        return

    database.save_pending_conversation_message(
        message.from_user.id,
        message.chat.id,
        message.message_id,
        content_type,
        content_text,
        created_at=datetime.now(config.timezone).isoformat(timespec="seconds"),
    )
    await message.answer(
        "<b>К какой заявке относится сообщение?</b>",
        reply_markup=conversation_selection_keyboard(open_orders, message.message_id),
    )


@priority_router.message(F.reply_to_message)
async def route_client_reply(
    message: Message,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    await _route_client_message(message, database, config, bot)


@router.message()
async def route_client_message(
    message: Message,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    await _route_client_message(message, database, config, bot)
