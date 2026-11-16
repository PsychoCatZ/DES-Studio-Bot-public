from __future__ import annotations

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from callbacks import OrderCallback
from config import Config
from database import Database, OrderCreate
from keyboards.admin import admin_order_keyboard
from keyboards.catalog import service_keyboard
from keyboards.main import main_menu_keyboard
from keyboards.order import (
    confirmation_keyboard,
    direction_keyboard,
    service_selection_keyboard,
    step_keyboard,
    success_keyboard,
)
from states.order import OrderStates
from utils.catalog_loader import Catalog
from utils.formatting import h, order_summary, service_card
from utils.screens import show_callback_screen


router = Router(name="order")

CUSTOM_SERVICE_ID = "custom-development"
ORDER_SELECTION_TEXT = (
    "<b>📝 Оставить заявку</b>\n\n"
    "Выберите услугу или укажите «Другая задача»."
)

MAX_LENGTHS = {"description": 1200}


async def _text_value(message: Message, field: str) -> str | None:
    value = (message.text or "").strip()
    if not value:
        await message.answer("Пожалуйста, отправьте ответ текстом.")
        return None
    limit = MAX_LENGTHS[field]
    if len(value) > limit:
        await message.answer(f"Ответ слишком длинный. Сократите его до {limit} символов.")
        return None
    return value


def _description_prompt(data: dict[str, object]) -> str:
    if data.get("is_custom_service"):
        return (
            "<b>Опишите задачу</b>\n\n"
            "Что нужно сделать и какой результат вы хотите получить?\n\n"
            "Можно пропустить этот шаг."
        )
    return (
        f"<b>Опишите требования к услуге «{h(data.get('service_title'))}»</b>\n\n"
        "Напишите требования или техническое задание текстом.\n\n"
        "Можно пропустить этот шаг."
    )


async def _show_description_from_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await show_callback_screen(
        callback,
        _description_prompt(await state.get_data()),
        step_keyboard(allow_skip=True),
    )


async def _show_confirmation_message(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderStates.confirm)
    await message.answer(order_summary(await state.get_data()), reply_markup=confirmation_keyboard())


async def _load_saved_referral(
    state: FSMContext,
    telegram_user_id: int,
    database: Database,
) -> None:
    referral = database.get_client_referral(telegram_user_id)
    source = database.get_manual_source(telegram_user_id) if not referral else None
    referrer_name = None
    if referral:
        referrer_name = referral["display_name"] or (
            f"@{referral['username']}" if referral["username"] else None
        )
        referrer_name = referrer_name or f"Telegram ID {referral['referrer_user_id']}"
    await state.update_data(
        referral_source=(f"рекомендация от {referrer_name}" if referral else (
            source["referral_source"] if source else None
        )),
        referrer_user_id=int(referral["referrer_user_id"]) if referral else None,
        referral_code=referral["referral_code"] if referral else None,
        referral_automatic=bool(referral),
        referral_known=bool(referral or source),
    )


@router.callback_query(OrderCallback.filter(F.action == "start"))
async def start_order(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    state: FSMContext,
    catalog: Catalog,
    database: Database,
) -> None:
    await state.clear()
    await _load_saved_referral(state, callback.from_user.id, database)
    if callback_data.ref:
        service = catalog.get_service(callback_data.ref)
        if service is None:
            await show_callback_screen(
                callback,
                "Услуга недоступна. Выберите другую услугу.",
                main_menu_keyboard(catalog),
            )
            return
        await state.update_data(
            service_id=service.id,
            service_title=service.title,
            source_service_id=service.id,
            source_category_id=service.category_id,
            entry_point="card",
            is_custom_service=service.id == CUSTOM_SERVICE_ID,
        )
        await state.set_state(OrderStates.description)
        await _show_description_from_callback(callback, state)
        return

    await state.set_state(OrderStates.choosing_service)
    await show_callback_screen(
        callback,
        ORDER_SELECTION_TEXT,
        direction_keyboard(catalog),
    )


@router.callback_query(
    OrderStates.choosing_service,
    OrderCallback.filter(F.action == "category"),
)
async def choose_order_category(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    state: FSMContext,
    catalog: Catalog,
) -> None:
    category = catalog.get_category(callback_data.ref)
    if category is None:
        await callback.answer("Направление недоступно", show_alert=True)
        return
    await show_callback_screen(
        callback,
        f"<b>{h(category.title)}</b>\n\nВыберите услугу:",
        service_selection_keyboard(catalog, category.id),
    )


@router.callback_query(
    OrderStates.choosing_service,
    OrderCallback.filter(F.action == "select"),
)
async def choose_order_service(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    state: FSMContext,
    catalog: Catalog,
) -> None:
    service = catalog.get_service(callback_data.ref)
    if service is None:
        await callback.answer("Услуга недоступна", show_alert=True)
        return
    await state.update_data(
        service_id=service.id,
        service_title=service.title,
        source_service_id="",
        source_category_id=service.category_id,
        entry_point="main",
        is_custom_service=service.id == CUSTOM_SERVICE_ID,
    )
    await state.set_state(OrderStates.description)
    await _show_description_from_callback(callback, state)


@router.callback_query(
    OrderStates.choosing_service,
    OrderCallback.filter(F.action == "selection_back"),
)
async def order_selection_back(
    callback: CallbackQuery,
    catalog: Catalog,
) -> None:
    await show_callback_screen(callback, ORDER_SELECTION_TEXT, direction_keyboard(catalog))


@router.message(OrderStates.description)
async def receive_description(message: Message, state: FSMContext) -> None:
    value = await _text_value(message, "description")
    if value is None:
        return
    await state.update_data(description=value)
    await _show_confirmation_message(message, state)


@router.callback_query(OrderStates.description, OrderCallback.filter(F.action == "skip"))
async def skip_description(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(description="")
    await state.set_state(OrderStates.confirm)
    await show_callback_screen(
        callback,
        order_summary(await state.get_data()),
        confirmation_keyboard(),
    )


@router.callback_query(OrderCallback.filter(F.action == "back"))
async def order_back(
    callback: CallbackQuery,
    state: FSMContext,
    catalog: Catalog,
    database: Database,
) -> None:
    current = await state.get_state()
    data = await state.get_data()
    if current == OrderStates.description.state:
        source_service_id = str(data.get("source_service_id") or "")
        if source_service_id:
            service = catalog.get_service(source_service_id)
            await state.clear()
            if service:
                await show_callback_screen(callback, service_card(service), service_keyboard(service))
                return
        referral_data = {
            "referral_source": data.get("referral_source"),
            "referral_automatic": data.get("referral_automatic", False),
            "referral_known": data.get("referral_known", False),
            "referrer_user_id": data.get("referrer_user_id"),
            "referral_code": data.get("referral_code"),
        }
        await state.clear()
        await state.update_data(**referral_data)
        await state.set_state(OrderStates.choosing_service)
        await show_callback_screen(
            callback,
            (
                f"<b>{h(catalog.get_category(str(data.get('source_category_id'))).title)}</b>\n\n"
                "Выберите услугу:"
                if data.get("entry_point") == "main"
                and data.get("source_category_id") != "custom"
                and catalog.get_category(str(data.get("source_category_id")))
                else ORDER_SELECTION_TEXT
            ),
            (
                service_selection_keyboard(catalog, str(data.get("source_category_id")))
                if data.get("entry_point") == "main"
                and data.get("source_category_id") != "custom"
                and catalog.get_category(str(data.get("source_category_id")))
                else direction_keyboard(catalog)
            ),
        )
    elif current == OrderStates.confirm.state:
        await state.set_state(OrderStates.description)
        await _show_description_from_callback(callback, state)
    else:
        await state.clear()
        await show_callback_screen(
            callback,
            "Заявка отменена.",
            main_menu_keyboard(catalog),
        )


@router.callback_query(OrderCallback.filter(F.action == "restart"))
async def restart_order(
    callback: CallbackQuery,
    state: FSMContext,
    catalog: Catalog,
    database: Database,
) -> None:
    await state.clear()
    await _load_saved_referral(state, callback.from_user.id, database)
    await state.set_state(OrderStates.choosing_service)
    await show_callback_screen(
        callback,
        ORDER_SELECTION_TEXT,
        direction_keyboard(catalog),
    )


@router.callback_query(OrderCallback.filter(F.action == "cancel"))
async def cancel_order(
    callback: CallbackQuery,
    state: FSMContext,
    catalog: Catalog,
    database: Database,
) -> None:
    await state.clear()
    await show_callback_screen(
        callback,
        "Заявка отменена. Вы можете вернуться к ней в любое время.",
        main_menu_keyboard(catalog),
    )


def _admin_notification(
    order_id: int,
    data: dict[str, object],
    user: object,
    created_at: datetime,
) -> str:
    first_name = getattr(user, "first_name", "") or ""
    last_name = getattr(user, "last_name", "") or ""
    full_name = " ".join(part for part in (first_name, last_name) if part).strip() or "Не указано"
    username = getattr(user, "username", None)
    username_text = f"@{h(username)}" if username else "username не указан"
    raw_source = str(data.get("referral_source") or "").strip()
    source_text = raw_source[:1].upper() + raw_source[1:] if raw_source else "не указан"
    referral_code = str(data.get("referral_code") or "").strip()
    source_lines = f"<b>Источник:</b> {h(source_text)}\n"
    if referral_code:
        source_lines += f"<b>Реферальный код:</b> <code>{h(referral_code)}</code>\n"
    return (
        f"<b>🐈 НОВАЯ ЗАЯВКА DES STUDIO #{order_id}</b>\n\n"
        f"<b>Услуга:</b>\n{h(data.get('service_title'))}\n\n"
        f"<b>Клиент:</b>\n{h(full_name)}\n{username_text}\n"
        f"Telegram ID: {h(getattr(user, 'id', None))}\n\n"
        f"<b>Задача:</b>\n{h(data.get('description'))}\n\n"
        f"{source_lines}\n"
        f"<b>Дата:</b>\n{created_at.strftime('%d.%m.%Y %H:%M')}"
    )


@router.callback_query(OrderStates.confirm, OrderCallback.filter(F.action == "send"))
async def send_order(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    database: Database,
    config: Config,
) -> None:
    data = await state.get_data()
    user = callback.from_user
    created_iso = str(data.get("created_at") or "")
    if created_iso:
        created_at = datetime.fromisoformat(created_iso)
    else:
        created_at = datetime.now(config.timezone)
        created_iso = created_at.isoformat(timespec="seconds")
        await state.update_data(created_at=created_iso)

    order = OrderCreate(
        telegram_user_id=user.id,
        telegram_chat_id=(
            callback.message.chat.id
            if isinstance(callback.message, Message)
            else user.id
        ),
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        service_id=str(data.get("service_id") or "") or None,
        service_title=str(data["service_title"]),
        description=str(data.get("description") or ""),
        materials="",
        desired_deadline=None,
        budget=None,
        comment=None,
        referral_source=data.get("referral_source") or None,
        referrer_user_id=(
            int(data["referrer_user_id"])
            if data.get("referrer_user_id")
            else None
        ),
        referral_code=data.get("referral_code") or None,
        created_at=created_iso,
    )
    order_id = int(data.get("order_id") or 0)
    if order_id:
        database.update_order(order_id, order)
    else:
        order_id = database.create_order(order)
        await state.update_data(order_id=order_id)

    if order.referral_source and not data.get("referral_automatic"):
        database.remember_manual_source(
            user.id,
            order.referral_source,
            created_at=created_iso,
        )

    await bot.send_message(
        config.admin_chat_id,
        _admin_notification(order_id, await state.get_data(), user, created_at),
        reply_markup=admin_order_keyboard(order_id),
    )
    database.mark_notified(order_id, datetime.now(config.timezone).isoformat(timespec="seconds"))
    await state.clear()
    await show_callback_screen(
        callback,
        f"<b>✅ Заявка #{order_id} отправлена.</b>\n\n"
        "Я ознакомлюсь с задачей и свяжусь с вами\n"
        "для уточнения деталей, стоимости и срока.",
        success_keyboard(),
    )
