from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from aiogram.types import Chat, ForceReply, Message, User

from callbacks import ClientReplyOrderCallback
from config import Config
from database import Database, OrderCreate
from handlers.admin_reply import deliver_admin_reply
from handlers.conversation import create_client_reply_prompt, route_client_message


def make_order(user_id: int, chat_id: int, title: str, username: str | None = None) -> OrderCreate:
    return OrderCreate(
        telegram_user_id=user_id,
        telegram_chat_id=chat_id,
        username=username,
        first_name="Клиент",
        last_name=None,
        service_id="service",
        service_title=title,
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


class FakeBot:
    def __init__(self) -> None:
        self.next_message_id = 100
        self.sent: list[tuple[str, int, str | None, dict[str, object]]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.next_message_id += 1
        self.sent.append(("message", chat_id, text, kwargs))
        return SimpleNamespace(message_id=self.next_message_id)

    async def copy_message(self, chat_id: int, from_chat_id: int, message_id: int, **kwargs):
        self.next_message_id += 1
        self.sent.append(("copy", chat_id, kwargs.get("caption"), kwargs))
        return SimpleNamespace(message_id=self.next_message_id)


class FakeClientMessage:
    def __init__(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        *,
        text: str | None = None,
        reply_to_message_id: int | None = None,
        photo: bool = False,
        document: bool = False,
        caption: str | None = None,
    ) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=chat_id)
        self.message_id = message_id
        self.text = text
        self.caption = caption
        self.photo = [object()] if photo else None
        self.document = object() if document else None
        self.reply_to_message = (
            SimpleNamespace(message_id=reply_to_message_id)
            if reply_to_message_id is not None
            else None
        )
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


class FakeCallback:
    def __init__(self, message: Message, user_id: int) -> None:
        self.message = message
        self.from_user = User(id=user_id, is_bot=False, first_name="Клиент")
        self.answers: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append((text, show_alert))


class FakeAdminReply:
    def __init__(self, prompt_message_id: int, text: str) -> None:
        self.chat = SimpleNamespace(id=999)
        self.reply_to_message = SimpleNamespace(message_id=prompt_message_id)
        self.text = text
        self.caption = None
        self.photo = None
        self.document = None
        self.answers: list[str] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append(text)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(":memory:")
        self.database.initialize()
        self.config = Config("token", 999, Path(":memory:"), ZoneInfo("UTC"))
        self.bot = FakeBot()

    async def test_closed_conversation_does_not_forward_client_text(self) -> None:
        self.database.create_order(make_order(10, 110, "Лендинг"))
        message = FakeClientMessage(10, 110, 1, text="Можно дополнить?")

        await route_client_message(message, self.database, self.config, self.bot)

        self.assertFalse(self.bot.sent)
        self.assertIn("Возможность ответить", message.answers[-1][0])

    async def test_client_reply_button_uses_force_reply_and_persists_mapping(self) -> None:
        order_id = self.database.create_order(make_order(10, 110, "Лендинг"))
        self.database.open_conversation_with_message(
            order_id, 110, 70, "admin_to_client", opened_at="2026-09-18T01:00:00+00:00"
        )
        callback_message = Message(
            message_id=70,
            date=datetime.now(timezone.utc),
            chat=Chat(id=110, type="private"),
            from_user=User(id=10, is_bot=False, first_name="Клиент"),
            text="Ответ DES Studio",
        )
        callback = FakeCallback(callback_message, 10)

        await create_client_reply_prompt(
            callback,
            ClientReplyOrderCallback(order_id=order_id),
            self.database,
            self.config,
            self.bot,
        )

        reply_markup = self.bot.sent[-1][3]["reply_markup"]
        self.assertIsInstance(reply_markup, ForceReply)
        prompt_id = self.bot.next_message_id
        mapped = self.database.get_order_for_conversation_message(110, prompt_id)
        self.assertEqual(order_id, mapped["id"])

    async def test_single_open_conversation_accepts_plain_text_and_admin_reply(self) -> None:
        order_id = self.database.create_order(make_order(10, 110, "Лендинг"))
        self.database.open_conversation_with_message(
            order_id, 110, 70, "admin_to_client", opened_at="2026-09-18T01:00:00+00:00"
        )
        message = FakeClientMessage(10, 110, 2, text="Уточнение клиента")

        await route_client_message(message, self.database, self.config, self.bot)

        admin_delivery = self.bot.sent[0]
        self.assertEqual(999, admin_delivery[1])
        self.assertIn(f"заявке #{order_id}", admin_delivery[2])
        self.assertIn("Username: отсутствует", admin_delivery[2])
        admin_message_id = 101
        self.assertEqual(
            order_id,
            self.database.get_order_for_conversation_message(999, admin_message_id)["id"],
        )

        reply = FakeAdminReply(admin_message_id, "Ответ на уточнение")
        await deliver_admin_reply(reply, self.database, self.config, self.bot)
        self.assertEqual(110, self.bot.sent[-1][1])
        self.assertIn(f"по заявке #{order_id}", self.bot.sent[-1][2])

    async def test_reply_message_routes_correct_order_when_two_are_open(self) -> None:
        first = self.database.create_order(make_order(10, 110, "Лендинг"))
        second = self.database.create_order(make_order(10, 110, "Telegram-бот"))
        self.database.open_conversation_with_message(
            first, 110, 501, "admin_to_client", opened_at="2026-09-18T01:00:00+00:00"
        )
        self.database.open_conversation_with_message(
            second, 110, 502, "admin_to_client", opened_at="2026-09-18T01:01:00+00:00"
        )
        message = FakeClientMessage(
            10, 110, 3, text="Ответ именно по лендингу", reply_to_message_id=501
        )

        await route_client_message(message, self.database, self.config, self.bot)

        self.assertIn(f"заявке #{first}", self.bot.sent[0][2])
        self.assertNotIn(f"заявке #{second}", self.bot.sent[0][2])

    async def test_multiple_open_conversations_require_explicit_selection(self) -> None:
        first = self.database.create_order(make_order(10, 110, "Лендинг"))
        second = self.database.create_order(make_order(10, 110, "Telegram-бот"))
        self.database.open_conversation_with_message(
            first, 110, 501, "admin_to_client", opened_at="2026-09-18T01:00:00+00:00"
        )
        self.database.open_conversation_with_message(
            second, 110, 502, "admin_to_client", opened_at="2026-09-18T01:01:00+00:00"
        )
        message = FakeClientMessage(10, 110, 4, text="Без Reply")

        await route_client_message(message, self.database, self.config, self.bot)

        self.assertFalse(self.bot.sent)
        prompt, markup = message.answers[-1]
        self.assertIn("К какой заявке", prompt)
        callbacks = [row[0].callback_data for row in markup.inline_keyboard]
        self.assertTrue(any(f":{first}:4" in value for value in callbacks))
        self.assertTrue(any(f":{second}:4" in value for value in callbacks))
        self.assertIsNotNone(self.database.get_pending_conversation_message(110, 4))

    async def test_photo_is_copied_without_downloading(self) -> None:
        order_id = self.database.create_order(make_order(10, 110, "Лендинг"))
        self.database.open_conversation_with_message(
            order_id, 110, 70, "admin_to_client", opened_at="2026-09-18T01:00:00+00:00"
        )
        message = FakeClientMessage(
            10, 110, 5, photo=True, caption="Скриншот ошибки"
        )

        await route_client_message(message, self.database, self.config, self.bot)

        self.assertEqual("copy", self.bot.sent[0][0])
        self.assertIn("Скриншот ошибки", self.bot.sent[0][2])


if __name__ == "__main__":
    unittest.main()
