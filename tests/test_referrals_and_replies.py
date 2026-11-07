from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from aiogram.types import Chat, Message, User
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from callbacks import ReplyOrderCallback
from config import Config
from database import Database, OrderCreate
from handlers.admin_reply import (
    create_admin_reply_prompt,
    deliver_admin_reply,
    explain_unlinked_admin_message,
)
from handlers.referrals import referral_link_callback, referral_link_command
from keyboards.admin import admin_order_keyboard


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, dict[str, object]]] = []
        self.next_message_id = 100

    async def get_me(self):
        return SimpleNamespace(username="DES_StudioBot")

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.next_message_id += 1
        self.messages.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=self.next_message_id)


class BlockedBot(FakeBot):
    async def send_message(self, chat_id: int, text: str, **kwargs):
        raise TelegramForbiddenError(
            method=SendMessage(chat_id=chat_id, text=text),
            message="bot was blocked by the user",
        )


class FakeCommandMessage:
    def __init__(self, user_id: int) -> None:
        self.from_user = SimpleNamespace(
            id=user_id,
            first_name="Иван",
            last_name="Иванов",
            username="ivan",
        )
        self.answers: list[str] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append(text)


class FakeCallback:
    def __init__(self, message: Message) -> None:
        self.message = message
        self.from_user = message.from_user
        self.answers: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append((text, show_alert))


class FakeAdminReply:
    def __init__(self, admin_chat_id: int, prompt_message_id: int, text: str) -> None:
        self.chat = SimpleNamespace(id=admin_chat_id)
        self.reply_to_message = SimpleNamespace(message_id=prompt_message_id)
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append(text)


def make_order(user_id: int, chat_id: int, title: str) -> OrderCreate:
    return OrderCreate(
        telegram_user_id=user_id,
        telegram_chat_id=chat_id,
        username=None,
        first_name=title,
        last_name=None,
        service_id="telegram-bot",
        service_title="Telegram-бот",
        description="Описание",
        materials="Нет",
        desired_deadline=None,
        budget=None,
        comment=None,
        referral_source=None,
        referrer_user_id=None,
        referral_code=None,
        created_at="2026-09-18T00:00:00+00:00",
    )


class ReferralAndReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_ref_command_returns_same_neutral_personal_link(self) -> None:
        database = Database(":memory:")
        database.initialize()
        config = Config("token", 999, Path(":memory:"), ZoneInfo("UTC"))
        message = FakeCommandMessage(700)
        bot = FakeBot()

        await referral_link_command(message, database, config, bot)
        first_code = database.get_or_create_referral_code(
            700,
            display_name="Иван Иванов",
            username="ivan",
            created_at="2026-09-18T01:00:00+00:00",
        )["referral_code"]
        await referral_link_command(message, database, config, bot)

        expected = f"https://t.me/DES_StudioBot?start=ref_{first_code}"
        self.assertIn(expected, message.answers[0])
        self.assertIn(expected, message.answers[1])
        combined = " ".join(message.answers).lower()
        for forbidden in ("партн", "комисс", "выплат", "заработ"):
            self.assertNotIn(forbidden, combined)

        callback = SimpleNamespace(
            from_user=User(
                id=700,
                is_bot=False,
                first_name="Иван",
                last_name="Иванов",
                username="ivan",
            ),
            message=object(),
        )
        from unittest.mock import AsyncMock, patch

        screen = AsyncMock()
        with patch("handlers.referrals.show_callback_screen", new=screen):
            await referral_link_callback(callback, database, config, bot)
        self.assertEqual(message.answers[0], screen.await_args.args[1])

    async def test_order_notification_keyboard_contains_order_id(self) -> None:
        callback = admin_order_keyboard(41).inline_keyboard[0][0].callback_data
        self.assertEqual(ReplyOrderCallback(order_id=41).pack(), callback)

    async def test_concurrent_admin_reply_prompts_route_to_correct_clients(self) -> None:
        database = Database(":memory:")
        database.initialize()
        first_id = database.create_order(make_order(11, 1111, "Вася"))
        second_id = database.create_order(make_order(22, 2222, "Петя"))
        config = Config("token", 999, Path(":memory:"), ZoneInfo("UTC"))
        bot = FakeBot()
        admin_message = Message(
            message_id=10,
            date=datetime.now(timezone.utc),
            chat=Chat(id=999, type="private"),
            from_user=User(id=999, is_bot=False, first_name="Admin"),
            text="Уведомление",
        )
        callback = FakeCallback(admin_message)

        await create_admin_reply_prompt(
            callback, ReplyOrderCallback(order_id=first_id), database, config, bot
        )
        first_prompt_id = bot.next_message_id
        first_prompt_kwargs = bot.messages[-1][2]
        self.assertEqual("ForceReply", type(first_prompt_kwargs["reply_markup"]).__name__)
        self.assertTrue(first_prompt_kwargs["reply_markup"].selective)
        self.assertIn("Введите ответ клиенту:", bot.messages[-1][1])
        await create_admin_reply_prompt(
            callback, ReplyOrderCallback(order_id=second_id), database, config, bot
        )
        second_prompt_id = bot.next_message_id

        first_reply = FakeAdminReply(999, first_prompt_id, "Ответ Васе")
        second_reply = FakeAdminReply(999, second_prompt_id, "Ответ Пете")
        await deliver_admin_reply(first_reply, database, config, bot)
        await deliver_admin_reply(second_reply, database, config, bot)

        client_deliveries = [item for item in bot.messages if item[0] != 999]
        self.assertEqual(1111, client_deliveries[0][0])
        self.assertIn("Ответ Васе", client_deliveries[0][1])
        self.assertEqual(2222, client_deliveries[1][0])
        self.assertIn("Ответ Пете", client_deliveries[1][1])
        self.assertIn(f"по заявке #{first_id}", client_deliveries[0][1])
        self.assertEqual(
            f"client_reply:{first_id}",
            client_deliveries[0][2]["reply_markup"].inline_keyboard[0][0].callback_data,
        )
        self.assertIsNotNone(database.get_order(first_id)["conversation_opened_at"])
        self.assertIsNotNone(database.get_order(second_id)["conversation_opened_at"])
        self.assertIn(f"#{first_id}", first_reply.answers[-1])
        self.assertIn(f"#{second_id}", second_reply.answers[-1])

    async def test_unlinked_admin_message_explains_how_to_reply(self) -> None:
        config = Config("token", 999, Path(":memory:"), ZoneInfo("UTC"))
        message = FakeAdminReply(999, 0, "Обычное сообщение")
        message.reply_to_message = None
        await explain_unlinked_admin_message(message, config)
        self.assertIn("⚠️ Не удалось определить заявку", message.answers[-1])
        self.assertIn("Ответить клиенту", message.answers[-1])

    async def test_blocked_client_produces_admin_message_without_exception(self) -> None:
        database = Database(":memory:")
        database.initialize()
        order_id = database.create_order(make_order(33, 3333, "Маша"))
        database.save_admin_reply_prompt(
            999,
            501,
            order_id,
            created_at="2026-09-18T00:00:00+00:00",
        )
        config = Config("token", 999, Path(":memory:"), ZoneInfo("UTC"))
        reply = FakeAdminReply(999, 501, "Ответ")
        with self.assertLogs("handlers.admin_reply", level="WARNING"):
            await deliver_admin_reply(reply, database, config, BlockedBot())
        self.assertIn("Не удалось доставить", reply.answers[-1])
        self.assertIn(f"#{order_id}", reply.answers[-1])
        self.assertIsNone(database.get_order(order_id)["conversation_opened_at"])


if __name__ == "__main__":
    unittest.main()
