from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import ClientReplyOrderCallback, ClientSelectOrderCallback


def client_reply_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"💬 Ответить по заявке #{order_id}",
        callback_data=ClientReplyOrderCallback(order_id=order_id),
    )
    return builder.as_markup()


def conversation_selection_keyboard(
    orders: Sequence[object],
    client_message_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        title = str(order["service_title"])
        if len(title) > 38:
            title = f"{title[:35]}…"
        builder.button(
            text=f"#{order['id']} {title}",
            callback_data=ClientSelectOrderCallback(
                order_id=int(order["id"]),
                client_message_id=client_message_id,
            ),
        )
    builder.adjust(1)
    return builder.as_markup()
