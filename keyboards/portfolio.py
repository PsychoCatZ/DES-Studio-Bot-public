from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import NavCallback


def portfolio_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🐈 Портал студии", url="https://example.org/")
    builder.button(text="💻 GitHub студии", url="https://github.com/your-username")
    builder.button(text="📞 Контакты", callback_data=NavCallback(action="contacts"))
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(1)
    return builder.as_markup()


def contacts_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✈️ Telegram @your_username", url="https://t.me/your_username")
    builder.button(text="💬 WhatsApp", url="https://wa.me/70000000001")
    builder.button(text="🏠 Главное меню", callback_data=NavCallback(action="home"))
    builder.adjust(1)
    return builder.as_markup()
