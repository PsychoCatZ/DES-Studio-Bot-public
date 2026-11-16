from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from callbacks import OrderCallback
from config import BASE_DIR, Config
from database import Database
from handlers.order import (
    choose_order_category,
    choose_order_service,
    receive_description,
    send_order,
    skip_description,
    order_back,
    start_order,
)
from handlers.start import start_command
from states.order import OrderStates
from utils.catalog_loader import load_catalog


class FakeMessage:
    def __init__(self, text: str = "", *, user_id: int | None = None) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id) if user_id else None
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> SimpleNamespace:
        self.messages.append((chat_id, text))
        return SimpleNamespace(message_id=len(self.messages))


def state_context(user_id: int) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id),
    )


def fake_user(user_id: int, username: str | None = "client") -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        username=username,
        first_name="Анна",
        last_name="Иванова",
    )


class OrderFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.catalog = load_catalog(BASE_DIR / "data" / "catalog.json")

    async def test_specific_service_uses_contextual_prompt(self) -> None:
        database = Database(":memory:")
        database.initialize()
        state = state_context(101)
        callback = SimpleNamespace(from_user=fake_user(101), message=object())
        screen = AsyncMock()
        with patch("handlers.order.show_callback_screen", new=screen):
            await start_order(
                callback,
                OrderCallback(action="start", ref="telegram-bot"),
                state,
                self.catalog,
                database,
            )
        prompt = screen.await_args.args[1]
        self.assertIn("Опишите требования к услуге «Telegram-бот»", prompt)
        self.assertIn("техническое задание текстом", prompt)
        self.assertIn("Можно пропустить", prompt)
        self.assertNotIn("Что нужно сделать", prompt)

    async def test_main_menu_selects_exact_service_and_custom_uses_general_prompt(self) -> None:
        database = Database(":memory:")
        database.initialize()
        callback = SimpleNamespace(from_user=fake_user(102), message=object())
        state = state_context(102)
        screen = AsyncMock()
        with patch("handlers.order.show_callback_screen", new=screen):
            await start_order(
                callback, OrderCallback(action="start"), state, self.catalog, database
            )
            await choose_order_category(
                callback,
                OrderCallback(action="category", ref="web"),
                state,
                self.catalog,
            )
            await choose_order_service(
                callback,
                OrderCallback(action="select", ref="landing"),
                state,
                self.catalog,
            )
        self.assertEqual("landing", (await state.get_data())["service_id"])
        self.assertIn("Опишите требования к услуге «Лендинг»", screen.await_args.args[1])

        custom_state = state_context(103)
        custom_callback = SimpleNamespace(from_user=fake_user(103), message=object())
        custom_screen = AsyncMock()
        with patch("handlers.order.show_callback_screen", new=custom_screen):
            await start_order(
                custom_callback,
                OrderCallback(action="start"),
                custom_state,
                self.catalog,
                database,
            )
            await choose_order_service(
                custom_callback,
                OrderCallback(action="select", ref="custom-development"),
                custom_state,
                self.catalog,
            )
        custom_prompt = custom_screen.await_args.args[1]
        self.assertIn("Что нужно сделать и какой результат вы хотите получить?", custom_prompt)
        self.assertNotIn("Опишите требования к услуге", custom_prompt)

    async def test_referral_survives_start_and_repeat_order(self) -> None:
        database = Database(":memory:")
        database.initialize()
        first = database.get_or_create_referral_code(
            9001,
            display_name="Voks",
            username="voks",
            created_at="2026-09-18T00:00:00+00:00",
        )
        second = database.get_or_create_referral_code(
            9002,
            display_name="Other",
            username=None,
            created_at="2026-09-18T00:00:00+00:00",
        )
        config = Config("token", 999, Path(":memory:"), ZoneInfo("UTC"))
        message = FakeMessage("/start ref_voks", user_id=201)
        state = state_context(201)

        await start_command(
            message,
            state,
            self.catalog,
            database,
            config,
            SimpleNamespace(args=f"ref_{first['referral_code']}"),
        )
        self.assertEqual(9001, database.get_client_referral(201)["referrer_user_id"])
        self.assertNotIn(first["referral_code"], message.answers[0][0])

        await start_command(
            message,
            state,
            self.catalog,
            database,
            config,
            SimpleNamespace(args=None),
        )
        await start_command(
            message,
            state,
            self.catalog,
            database,
            config,
            SimpleNamespace(args=f"ref_{second['referral_code']}"),
        )
        self.assertEqual(9001, database.get_client_referral(201)["referrer_user_id"])
        self.assertNotEqual(9002, database.get_client_referral(201)["referrer_user_id"])

        callback = SimpleNamespace(from_user=fake_user(201, None), message=object())
        order_state = state_context(201)
        with patch("handlers.order.show_callback_screen", new=AsyncMock()):
            await start_order(
                callback,
                OrderCallback(action="start", ref="telegram-bot"),
                order_state,
                self.catalog,
                database,
            )
        await receive_description(FakeMessage("Нужен бот"), order_state)
        self.assertEqual(OrderStates.confirm.state, await order_state.get_state())

        bot = FakeBot()
        with patch("handlers.order.show_callback_screen", new=AsyncMock()):
            await send_order(callback, order_state, bot, database, config)
        row = database.get_order(1)
        self.assertEqual(9001, row["referrer_user_id"])
        self.assertEqual(first["referral_code"], row["referral_code"])
        self.assertEqual("рекомендация от Voks", row["referral_source"])
        self.assertIn("<b>Источник:</b> Рекомендация от Voks", bot.messages[0][1])
        self.assertIn(
            f"<b>Реферальный код:</b> <code>{first['referral_code']}</code>",
            bot.messages[0][1],
        )
        self.assertIn("НОВАЯ ЗАЯВКА DES STUDIO #1", bot.messages[0][1])

        repeat_state = state_context(201)
        with patch("handlers.order.show_callback_screen", new=AsyncMock()):
            await start_order(
                callback,
                OrderCallback(action="start", ref="landing"),
                repeat_state,
                self.catalog,
                database,
            )
        repeat_data = await repeat_state.get_data()
        self.assertTrue(repeat_data["referral_known"])
        self.assertEqual(first["referral_code"], repeat_data["referral_code"])

    async def test_saved_manual_source_is_reused_without_question(self) -> None:
        database = Database(":memory:")
        database.initialize()
        database.remember_manual_source(301, "@friend", created_at="2026-11-16T00:00:00+00:00")
        state = state_context(301)
        callback = SimpleNamespace(from_user=fake_user(301), message=object())
        with patch("handlers.order.show_callback_screen", new=AsyncMock()):
            await start_order(
                callback, OrderCallback(action="start", ref="landing"),
                state, self.catalog, database,
            )
        message = FakeMessage("Требования")
        await receive_description(message, state)
        self.assertEqual(OrderStates.confirm.state, await state.get_state())
        self.assertEqual(1, len(message.answers))
        self.assertNotIn("Материалы:", message.answers[0][0])
        bot = FakeBot()
        with patch("handlers.order.show_callback_screen", new=AsyncMock()):
            await send_order(
                callback, state, bot, database,
                Config("token", 999, Path(":memory:"), ZoneInfo("UTC")),
            )
        self.assertEqual("@friend", database.get_order(1)["referral_source"])

    async def test_skip_description_sends_order_without_any_questionnaire(self) -> None:
        database = Database(":memory:")
        database.initialize()
        state = state_context(401)
        callback = SimpleNamespace(from_user=fake_user(401, None), message=object())
        screen = AsyncMock()
        with patch("handlers.order.show_callback_screen", new=screen):
            await start_order(
                callback, OrderCallback(action="start", ref="landing"),
                state, self.catalog, database,
            )
            buttons = screen.await_args.args[2].inline_keyboard
            self.assertIn("ord:skip:", [b.callback_data for row in buttons for b in row])
            await skip_description(callback, state)
            self.assertEqual(OrderStates.confirm.state, await state.get_state())
            summary = screen.await_args.args[1]
            for label in ("Материалы:", "Бюджет:", "Желаемый срок:", "Дополнительно:"):
                self.assertNotIn(label, summary)
            await order_back(callback, state, self.catalog, database)
            self.assertEqual(OrderStates.description.state, await state.get_state())
            await skip_description(callback, state)
            bot = FakeBot()
            await send_order(
                callback, state, bot, database,
                Config("token", 999, Path(":memory:"), ZoneInfo("UTC")),
            )
        order = database.get_order(1)
        self.assertEqual("landing", order["service_id"])
        self.assertEqual("", order["description"])
        self.assertEqual("", order["materials"])
        self.assertIsNone(order["referral_source"])
        self.assertIsNotNone(order["notified_at"])
        self.assertIsNone(await state.get_state())
        self.assertIn("НОВАЯ ЗАЯВКА DES STUDIO #1", bot.messages[0][1])
        self.assertNotIn("Материалы:", bot.messages[0][1])


if __name__ == "__main__":
    unittest.main()
