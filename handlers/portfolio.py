from aiogram import F, Router
from aiogram.types import CallbackQuery

from callbacks import NavCallback, PortfolioCallback
from keyboards.portfolio import contacts_keyboard, portfolio_keyboard
from utils.screens import show_callback_screen


router = Router(name="portfolio")


@router.callback_query(NavCallback.filter(F.action == "portfolio"))
async def show_portfolio(callback: CallbackQuery) -> None:
    await show_callback_screen(
        callback,
        "<b>📁 Портфолио</b>\n\nПроекты и разработки — на портале и GitHub:",
        portfolio_keyboard(),
    )


@router.callback_query(PortfolioCallback.filter())
async def show_project(callback: CallbackQuery) -> None:
    # Previously sent project buttons remain useful after the update.
    await show_portfolio(callback)


@router.callback_query(NavCallback.filter(F.action == "contacts"))
async def show_contacts(callback: CallbackQuery) -> None:
    await show_callback_screen(
        callback,
        "<b>📞 Прямые контакты</b>\n\n"
        "Телефон (только СМС): <code>+7 000 000 00 00</code>\n"
        "Telegram: @your_username\n"
        "WhatsApp: <code>+7 000 000-00-01</code>",
        contacts_keyboard(),
    )
