from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import CategoryCallback, NavCallback, OrderCallback, ServiceCallback
from utils.catalog_loader import Catalog, Service


def category_keyboard(catalog: Catalog, category_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in catalog.services_for_category(category_id):
        builder.button(text=service.title, callback_data=ServiceCallback(service_id=service.id))
    builder.adjust(1)
    builder.button(text="📝 Оставить заявку", callback_data=OrderCallback(action="start"))
    builder.button(text="◀️ Назад", callback_data=NavCallback(action="home"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(*([1] * len(catalog.services_for_category(category_id))), 1, 2)
    return builder.as_markup()

def service_keyboard(service: Service) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📝 Заказать",
        callback_data=OrderCallback(action="start", ref=service.id),
    )
    builder.button(
        text="◀️ Назад",
        callback_data=CategoryCallback(category_id=service.category_id, view="catalog"),
    )
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(1, 2)
    return builder.as_markup()


def prices_keyboard(catalog: Catalog) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in catalog.categories:
        builder.button(
            text=category.short_title,
            callback_data=CategoryCallback(category_id=category.id, view="prices"),
        )
    builder.adjust(2)
    builder.button(text="📝 Оставить заявку", callback_data=OrderCallback(action="start"))
    builder.button(text="◀️ Назад", callback_data=NavCallback(action="home"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(2, 2, 2, 1, 1, 2)
    return builder.as_markup()


def price_category_keyboard(category_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Оставить заявку", callback_data=OrderCallback(action="start"))
    builder.button(text="◀️ Назад", callback_data=NavCallback(action="prices"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(1, 2)
    return builder.as_markup()
