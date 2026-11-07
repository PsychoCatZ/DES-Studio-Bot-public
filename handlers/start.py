from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from callbacks import NavCallback
from config import Config
from database import Database
from keyboards.main import main_menu_keyboard
from utils.catalog_loader import Catalog
from utils.screens import show_callback_screen
from utils.referrals import is_valid_referral_code


router = Router(name="start")

WELCOME = (
    "<b>🐈 DES Studio</b>\n\n"
    "Разработка сайтов, ботов, автоматизации\n"
    "и AI-инструментов под конкретные задачи."
)


@router.message(CommandStart())
async def start_command(
    message: Message,
    state: FSMContext,
    catalog: Catalog,
    database: Database,
    config: Config,
    command: CommandObject,
) -> None:
    await state.clear()
    payload = (command.args or "").strip()
    if payload.startswith("ref_") and message.from_user:
        referral_code = payload[4:]
        if is_valid_referral_code(referral_code):
            owner = database.get_referral_owner(referral_code)
            if owner:
                database.bind_client_to_referrer(
                    message.from_user.id,
                    int(owner["telegram_user_id"]),
                    str(owner["referral_code"]),
                    created_at=datetime.now(config.timezone).isoformat(timespec="seconds"),
                )
    await message.answer(
        WELCOME,
        reply_markup=main_menu_keyboard(catalog),
    )


@router.callback_query(NavCallback.filter(F.action == "home"))
async def home_callback(
    callback: CallbackQuery,
    state: FSMContext,
    catalog: Catalog,
) -> None:
    await state.clear()
    await show_callback_screen(
        callback,
        WELCOME,
        main_menu_keyboard(catalog),
    )
