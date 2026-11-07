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
    receive_budget,
    receive_comment,
    receive_deadline,
    receive_description,
    receive_materials,
    receive_referral,
    send_order,
    skip_budget,
    skip_comment,
    skip_deadline,
    skip_referral,
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
        self.assertIn("пришлите техническое задание", prompt)
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
        await receive_materials(FakeMessage("Материалов нет"), order_state)
        await receive_deadline(FakeMessage("В течение месяца"), order_state)
        await receive_budget(FakeMessage("10 000 ₽"), order_state)
        await receive_comment(FakeMessage("Комментарий"), order_state)
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

    async def test_manual_source_without_deep_link_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "orders.db")
            database.initialize()
            state = state_context(301)
            callback = SimpleNamespace(from_user=fake_user(301), message=object())
            with patch("handlers.order.show_callback_screen", new=AsyncMock()):
                await start_order(
                    callback,
                    OrderCallback(action="start", ref="custom-development"),
                    state,
                    self.catalog,
                    database,
                )
            await receive_description(FakeMessage("Другая задача"), state)
            await receive_materials(FakeMessage("Есть описание"), state)
            await skip_deadline(callback, state)
            await skip_budget(callback, state)
            await skip_comment(callback, state)
            self.assertEqual(OrderStates.referral.state, await state.get_state())
            await receive_referral(FakeMessage("@friend"), state)
            self.assertEqual(OrderStates.confirm.state, await state.get_state())

            bot = FakeBot()
            config = Config("token", 999, Path(directory) / "orders.db", ZoneInfo("UTC"))
            with patch("handlers.order.show_callback_screen", new=AsyncMock()):
                await send_order(callback, state, bot, database, config)
            self.assertEqual("@friend", database.get_order(1)["referral_source"])
            self.assertEqual("@friend", database.get_manual_source(301)["referral_source"])
            self.assertIn("<b>Источник:</b> @friend", bot.messages[0][1])

    async def test_referral_question_can_be_skipped(self) -> None:
        state = state_context(401)
        await state.set_state(OrderStates.referral)
        callback = SimpleNamespace(from_user=fake_user(401), message=object())
        with patch("handlers.order.show_callback_screen", new=AsyncMock()):
            await skip_referral(callback, state)
        self.assertEqual(OrderStates.confirm.state, await state.get_state())
        self.assertIsNone((await state.get_data())["referral_source"])


if __name__ == "__main__":
    unittest.main()
