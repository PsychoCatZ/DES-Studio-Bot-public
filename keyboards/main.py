from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import CategoryCallback, NavCallback, OrderCallback
from utils.catalog_loader import Catalog


def main_menu_keyboard(catalog: Catalog) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in catalog.categories:
        builder.button(
            text=category.title,
            callback_data=CategoryCallback(category_id=category.id, view="catalog"),
        )
    builder.adjust(1)
    builder.button(text="📁 Портфолио", callback_data=NavCallback(action="portfolio"))
    builder.button(text="💰 Все цены", callback_data=NavCallback(action="prices"))
    builder.button(
        text="🔗 Получить реферальную ссылку",
        callback_data=NavCallback(action="referral_link"),
    )
    builder.button(text="📝 Оставить заявку", callback_data=OrderCallback(action="start"))
    builder.adjust(*([1] * len(catalog.categories)), 2, 1, 1)
    return builder.as_markup()
