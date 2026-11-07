from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Chat, Message, MessageEntity, Update, User

from bot import build_dispatcher, load_application_data
from config import BASE_DIR, Config
from database import Database, OrderCreate
from states.order import OrderStates


class FakeBot(Bot):
    def __init__(self) -> None:
        fake_token = "123456:" + "abcdefghijklmnopqrstuvwxyzABCDE1234567890"
        super().__init__(fake_token)
        self.calls: list[object] = []

    async def __call__(self, method, request_timeout=None):
        self.calls.append(method)
        if type(method).__name__ in {"SendMessage", "CopyMessage"}:
            return SimpleNamespace(message_id=900 + len(self.calls))
        return True


class DispatcherTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dispatcher = build_dispatcher()

    async def test_real_command_filter_and_dependency_injection(self) -> None:
        bot = FakeBot()
        dispatcher = self.dispatcher
        catalog, portfolio = load_application_data()
        database = Database(":memory:")
        database.initialize()
        referral = database.get_or_create_referral_code(
            909,
            display_name="Voks",
            username=None,
            created_at="2026-09-18T00:00:00+00:00",
        )
        config = Config("token", 1, Path(":memory:"), ZoneInfo("UTC"))
        update = Update(
            update_id=1,
            message=Message(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=Chat(id=505, type="private"),
                from_user=User(id=505, is_bot=False, first_name="Test"),
                text=f"/start ref_{referral['referral_code']}",
                entities=[MessageEntity(type="bot_command", offset=0, length=6)],
            ),
        )
        try:
            await dispatcher.feed_update(
                bot,
                update,
                catalog=catalog,
                portfolio=portfolio,
                database=database,
                config=config,
                project_root=BASE_DIR,
            )
        finally:
            await bot.session.close()

        self.assertEqual(909, database.get_client_referral(505)["referrer_user_id"])
        self.assertEqual("SendMessage", type(bot.calls[0]).__name__)

    async def test_client_reply_skips_admin_handler_and_reaches_conversation_router(self) -> None:
        bot = FakeBot()
        dispatcher = self.dispatcher
        catalog, portfolio = load_application_data()
        database = Database(":memory:")
        database.initialize()
        order_id = database.create_order(
            OrderCreate(
                telegram_user_id=505,
                telegram_chat_id=505,
                username=None,
                first_name="Test",
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
        )
        database.open_conversation_with_message(
            order_id,
            505,
            70,
            "admin_to_client",
            opened_at="2026-09-18T00:01:00+00:00",
        )
        config = Config("token", 999, Path(":memory:"), ZoneInfo("UTC"))
        storage_key = StorageKey(
            bot_id=bot.id,
            chat_id=505,
            user_id=505,
        )
        await dispatcher.storage.set_state(storage_key, OrderStates.materials)
        update = Update(
            update_id=2,
            message=Message(
                message_id=71,
                date=datetime.now(timezone.utc),
                chat=Chat(id=505, type="private"),
                from_user=User(id=505, is_bot=False, first_name="Test"),
                text="Ответ клиента",
                reply_to_message=Message(
                    message_id=70,
                    date=datetime.now(timezone.utc),
                    chat=Chat(id=505, type="private"),
                    from_user=User(id=123456, is_bot=True, first_name="Bot"),
                    text="Ответ DES Studio",
                ),
            ),
        )
        try:
            await dispatcher.feed_update(
                bot,
                update,
                catalog=catalog,
                portfolio=portfolio,
                database=database,
                config=config,
                project_root=BASE_DIR,
            )
        finally:
            await bot.session.close()

        admin_calls = [call for call in bot.calls if getattr(call, "chat_id", None) == 999]
        self.assertEqual(1, len(admin_calls))
        self.assertIn(f"заявке #{order_id}", admin_calls[0].text)
        self.assertEqual(
            OrderStates.materials.state,
            await dispatcher.storage.get_state(storage_key),
        )
        self.assertEqual(
            order_id,
            database.get_order_for_conversation_message(999, 901)["id"],
        )


if __name__ == "__main__":
    unittest.main()
