from aiogram import F, Router
from aiogram.types import CallbackQuery

from callbacks import CategoryCallback, NavCallback, ServiceCallback
from keyboards.catalog import (
    category_keyboard,
    price_category_keyboard,
    prices_keyboard,
    service_keyboard,
)
from keyboards.main import main_menu_keyboard
from utils.catalog_loader import Catalog
from utils.formatting import category_price_list, h, service_card
from utils.screens import show_callback_screen


router = Router(name="catalog")


@router.callback_query(CategoryCallback.filter(F.view == "catalog"))
async def show_category(
    callback: CallbackQuery,
    callback_data: CategoryCallback,
    catalog: Catalog,
) -> None:
    category = catalog.get_category(callback_data.category_id)
    if category is None:
        await show_callback_screen(
            callback,
            "Категория недоступна. Вернитесь в главное меню.",
            main_menu_keyboard(catalog),
        )
        return
    await show_callback_screen(
        callback,
        f"<b>{h(category.title)}</b>\n\nВыберите услугу:",
        category_keyboard(catalog, category.id),
    )

@router.callback_query(ServiceCallback.filter())
async def show_service(
    callback: CallbackQuery,
    callback_data: ServiceCallback,
    catalog: Catalog,
) -> None:
    service = catalog.get_service(callback_data.service_id)
    if service is None:
        await show_callback_screen(
            callback,
            "Услуга недоступна. Вернитесь в главное меню.",
            main_menu_keyboard(catalog),
        )
        return
    await show_callback_screen(callback, service_card(service), service_keyboard(service))


@router.callback_query(NavCallback.filter(F.action == "prices"))
async def show_prices(callback: CallbackQuery, catalog: Catalog) -> None:
    await show_callback_screen(
        callback,
        "<b>💰 Все цены</b>\n\nВыберите направление:",
        prices_keyboard(catalog),
    )


@router.callback_query(CategoryCallback.filter(F.view == "prices"))
async def show_category_prices(
    callback: CallbackQuery,
    callback_data: CategoryCallback,
    catalog: Catalog,
) -> None:
    category = catalog.get_category(callback_data.category_id)
    if category is None:
        await show_callback_screen(
            callback,
            "Категория недоступна. Вернитесь к списку цен.",
            prices_keyboard(catalog),
        )
        return
    services = catalog.services_for_category(category.id)
    await show_callback_screen(
        callback,
        category_price_list(category, services),
        price_category_keyboard(category.id),
    )
