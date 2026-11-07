from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database import Database, OrderCreate


def sample_order() -> OrderCreate:
    return OrderCreate(
        telegram_user_id=123,
        telegram_chat_id=123,
        username=None,
        first_name="Иван",
        last_name=None,
        service_id="telegram-bot",
        service_title="Telegram-бот",
        description="Нужен бот",
        materials="Материалов нет",
        desired_deadline=None,
        budget=None,
        comment=None,
        referral_source="voks",
        referrer_user_id=None,
        referral_code=None,
        created_at="2026-09-17T22:40:00+07:00",
    )


class DatabaseTests(unittest.TestCase):
    def test_order_survives_database_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.db"
            database = Database(path)
            database.initialize()
            order_id = database.create_order(sample_order())
            database.mark_notified(order_id, "2026-09-17T22:41:00+07:00")
            referral = database.get_or_create_referral_code(
                900,
                display_name="Источник",
                username=None,
                created_at="2026-09-17T22:41:00+07:00",
            )
            database.bind_client_to_referrer(
                123,
                900,
                referral["referral_code"],
                created_at="2026-09-17T22:42:00+07:00",
            )
            database.save_admin_reply_prompt(
                999,
                501,
                order_id,
                created_at="2026-09-17T22:43:00+07:00",
            )
            database.open_conversation_with_message(
                order_id,
                123,
                601,
                "admin_to_client",
                opened_at="2026-09-17T22:44:00+07:00",
            )

            reopened = Database(path)
            reopened.initialize()
            row = reopened.get_order(order_id)
            self.assertEqual(1, reopened.count_orders())
            self.assertEqual("new", row["status"])
            self.assertEqual(123, row["telegram_user_id"])
            self.assertEqual("voks", row["referral_source"])
            self.assertIsNotNone(row["notified_at"])
            same_referral = reopened.get_or_create_referral_code(
                900,
                display_name="Новое имя",
                username="new_name",
                created_at="2026-09-18T00:00:00+07:00",
            )
            self.assertEqual(referral["referral_code"], same_referral["referral_code"])
            self.assertEqual(900, reopened.get_client_referral(123)["referrer_user_id"])
            self.assertEqual(order_id, reopened.get_order_for_admin_prompt(999, 501)["id"])
            self.assertIsNotNone(row["conversation_opened_at"])
            self.assertEqual(
                order_id,
                reopened.get_order_for_conversation_message(123, 601)["id"],
            )

    def test_first_referral_attribution_cannot_be_overwritten(self) -> None:
        database = Database(":memory:")
        database.initialize()
        first = database.get_or_create_referral_code(
            1001,
            display_name="Voks",
            username="voks_user",
            created_at="2026-09-18T00:00:00+07:00",
        )
        second = database.get_or_create_referral_code(
            1002,
            display_name="Другой пользователь",
            username=None,
            created_at="2026-09-18T00:00:00+07:00",
        )
        self.assertTrue(
            database.bind_client_to_referrer(
                777, 1001, first["referral_code"],
                created_at="2026-09-18T00:01:00+07:00"
            )
        )
        self.assertFalse(
            database.bind_client_to_referrer(
                777, 1002, second["referral_code"],
                created_at="2026-09-18T00:02:00+07:00"
            )
        )
        attribution = database.get_client_referral(777)
        self.assertEqual(first["referral_code"], attribution["referral_code"])
        self.assertEqual(1001, attribution["referrer_user_id"])

    def test_self_referral_is_rejected(self) -> None:
        database = Database(":memory:")
        database.initialize()
        referral = database.get_or_create_referral_code(
            1001,
            display_name="Voks",
            username=None,
            created_at="2026-09-18T00:00:00+07:00",
        )
        self.assertFalse(
            database.bind_client_to_referrer(
                1001, 1001, referral["referral_code"],
                created_at="2026-09-18T00:01:00+07:00",
            )
        )
        self.assertIsNone(database.get_client_referral(1001))


if __name__ == "__main__":
    unittest.main()
