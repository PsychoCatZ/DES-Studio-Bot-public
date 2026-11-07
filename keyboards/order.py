from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import NavCallback, OrderCallback
from utils.catalog_loader import Catalog


def direction_keyboard(catalog: Catalog) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in catalog.categories:
        if category.id == "custom":
            continue
        builder.button(
            text=category.title,
            callback_data=OrderCallback(action="category", ref=category.id),
        )
    custom_services = catalog.services_for_category("custom")
    if custom_services:
        builder.button(
            text="🧩 Другая задача",
            callback_data=OrderCallback(action="select", ref=custom_services[0].id),
        )
    builder.adjust(1)
    builder.button(text="❌ Отмена", callback_data=OrderCallback(action="cancel"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(*([1] * len(catalog.categories)), 2)
    return builder.as_markup()


def service_selection_keyboard(catalog: Catalog, category_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    services = catalog.services_for_category(category_id)
    for service in services:
        builder.button(
            text=service.title,
            callback_data=OrderCallback(action="select", ref=service.id),
        )
    builder.adjust(1)
    builder.button(text="◀️ Назад", callback_data=OrderCallback(action="selection_back"))
    builder.button(text="❌ Отмена", callback_data=OrderCallback(action="cancel"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(*([1] * len(services)), 1, 2)
    return builder.as_markup()


def step_keyboard(*, allow_skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if allow_skip:
        builder.button(text="Пропустить", callback_data=OrderCallback(action="skip"))
    builder.button(text="◀️ Назад", callback_data=OrderCallback(action="back"))
    builder.button(text="❌ Отмена", callback_data=OrderCallback(action="cancel"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(1, 2 if allow_skip else 1, 1)
    return builder.as_markup()


def confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data=OrderCallback(action="send"))
    builder.button(text="✏️ Начать заново", callback_data=OrderCallback(action="restart"))
    builder.button(text="◀️ Назад", callback_data=OrderCallback(action="back"))
    builder.button(text="❌ Отмена", callback_data=OrderCallback(action="cancel"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(1, 1, 2, 1)
    return builder.as_markup()


def success_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    return builder.as_markup()
