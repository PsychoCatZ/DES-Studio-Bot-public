from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import ReplyOrderCallback


def admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💬 Ответить клиенту",
        callback_data=ReplyOrderCallback(order_id=order_id),
    )
    return builder.as_markup()
