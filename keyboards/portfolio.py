from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import NavCallback, OrderCallback, PortfolioCallback
from utils.catalog_loader import Portfolio


def portfolio_keyboard(portfolio: Portfolio) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for project in portfolio.projects:
        builder.button(
            text=project.title,
            callback_data=PortfolioCallback(project_id=project.id),
        )
    builder.adjust(1)
    builder.button(text="📝 Оставить заявку", callback_data=OrderCallback(action="start"))
    builder.button(text="◀️ Назад", callback_data=NavCallback(action="home"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(*([1] * len(portfolio.projects)), 1, 2)
    return builder.as_markup()

def portfolio_card_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Оставить заявку", callback_data=OrderCallback(action="start"))
    builder.button(text="◀️ Назад", callback_data=NavCallback(action="portfolio"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(1, 2)
    return builder.as_markup()
