from __future__ import annotations

import logging
from pathlib import Path

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message


logger = logging.getLogger(__name__)


async def show_callback_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    *,
    image: str | None = None,
    base_dir: Path | None = None,
) -> None:
    message = callback.message
    if not isinstance(message, Message):
        return

    try:
        await callback.answer()
    except TelegramBadRequest as exc:
        if "query is too old" not in str(exc).lower() and "query id is invalid" not in str(exc).lower():
            raise
        logger.info("Ignoring expired callback acknowledgement: %s", exc)
    if image:
        photo: str | FSInputFile = image
        if not image.startswith(("http://", "https://")):
            path = Path(image)
            if not path.is_absolute() and base_dir:
                path = base_dir / path
            if path.is_file():
                photo = FSInputFile(path)
            else:
                logger.warning("Portfolio image not found: %s", path)
                image = None
        if image:
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            await message.answer_photo(photo=photo, caption=text, reply_markup=reply_markup)
            return

    if message.photo:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        await message.answer(text, reply_markup=reply_markup)
        return

    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            await message.answer(text, reply_markup=reply_markup)
