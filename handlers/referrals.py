from __future__ import annotations

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User

from callbacks import NavCallback
from config import Config
from database import Database
from keyboards.referrals import referral_link_keyboard
from utils.formatting import h
from utils.screens import show_callback_screen


router = Router(name="referrals")


async def referral_link_text(
    user: User,
    database: Database,
    config: Config,
    bot: Bot,
) -> str:
    full_name = " ".join(
        part for part in (user.first_name, user.last_name) if part
    ).strip()
    referral = database.get_or_create_referral_code(
        user.id,
        display_name=full_name or None,
        username=user.username,
        created_at=datetime.now(config.timezone).isoformat(timespec="seconds"),
    )
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{referral['referral_code']}"
    return (
        "<b>🔗 Ваша персональная ссылка DES Studio:</b>\n"
        f"<code>{h(link)}</code>"
    )


@router.message(Command("ref"))
async def referral_link_command(
    message: Message,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    if not message.from_user:
        return
    await message.answer(
        await referral_link_text(message.from_user, database, config, bot)
    )


@router.callback_query(NavCallback.filter(F.action == "referral_link"))
async def referral_link_callback(
    callback: CallbackQuery,
    database: Database,
    config: Config,
    bot: Bot,
) -> None:
    await show_callback_screen(
        callback,
        await referral_link_text(callback.from_user, database, config, bot),
        referral_link_keyboard(),
    )
