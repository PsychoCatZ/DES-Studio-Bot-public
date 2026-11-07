from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery

from callbacks import NavCallback, PortfolioCallback
from keyboards.main import main_menu_keyboard
from keyboards.portfolio import portfolio_card_keyboard, portfolio_keyboard
from utils.catalog_loader import Catalog, Portfolio
from utils.formatting import portfolio_card
from utils.screens import show_callback_screen


router = Router(name="portfolio")


@router.callback_query(NavCallback.filter(F.action == "portfolio"))
async def show_portfolio(callback: CallbackQuery, portfolio: Portfolio) -> None:
    await show_callback_screen(
        callback,
        "<b>📁 Портфолио</b>\n\nВыберите проект:",
        portfolio_keyboard(portfolio),
    )

@router.callback_query(PortfolioCallback.filter())
async def show_project(
    callback: CallbackQuery,
    callback_data: PortfolioCallback,
    portfolio: Portfolio,
    catalog: Catalog,
    project_root: Path,
) -> None:
    project = portfolio.get(callback_data.project_id)
    if project is None:
        await show_callback_screen(
            callback,
            "Проект недоступен. Вернитесь в главное меню.",
            main_menu_keyboard(catalog),
        )
        return
    await show_callback_screen(
        callback,
        portfolio_card(project),
        portfolio_card_keyboard(),
        image=project.image,
        base_dir=project_root,
    )
