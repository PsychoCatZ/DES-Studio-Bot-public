from __future__ import annotations

import sqlite3
import secrets
from pathlib import Path

from database.models import OrderCreate


SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL,
    telegram_chat_id INTEGER,
    username TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT,
    service_id TEXT,
    service_title TEXT NOT NULL,
    description TEXT NOT NULL,
    materials TEXT NOT NULL,
    desired_deadline TEXT,
    budget TEXT,
    comment TEXT,
    referral_source TEXT,
    referrer_user_id INTEGER,
    referral_code TEXT,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'in_progress', 'completed', 'cancelled')),
    created_at TEXT NOT NULL,
    notified_at TEXT,
    conversation_opened_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_telegram_user_id
    ON orders(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders(status);
CREATE TABLE IF NOT EXISTS client_sources (
    telegram_user_id INTEGER PRIMARY KEY,
    referral_source TEXT NOT NULL,
    start_payload TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS referral_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    referral_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT,
    username TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS referral_attributions (
    referred_client_user_id INTEGER PRIMARY KEY,
    referrer_user_id INTEGER NOT NULL,
    referral_code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (referrer_user_id) REFERENCES referral_codes(telegram_user_id)
);
CREATE TABLE IF NOT EXISTS admin_reply_prompts (
    admin_chat_id INTEGER NOT NULL,
    admin_prompt_message_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (admin_chat_id, admin_prompt_message_id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    telegram_chat_id INTEGER NOT NULL,
    telegram_message_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (telegram_chat_id, telegram_message_id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_order_id
    ON conversation_messages(order_id);
CREATE TABLE IF NOT EXISTS pending_conversation_messages (
    telegram_user_id INTEGER NOT NULL,
    telegram_chat_id INTEGER NOT NULL,
    telegram_message_id INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    content_text TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (telegram_chat_id, telegram_message_id)
);
"""


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if str(path) != ":memory:" else Path(":memory:")
        self._memory_connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(":memory:")
                self._memory_connection.row_factory = sqlite3.Row
            return self._memory_connection
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(orders)").fetchall()
            }
            if "referral_source" not in columns:
                connection.execute("ALTER TABLE orders ADD COLUMN referral_source TEXT")
            if "telegram_chat_id" not in columns:
                connection.execute("ALTER TABLE orders ADD COLUMN telegram_chat_id INTEGER")
                connection.execute(
                    "UPDATE orders SET telegram_chat_id = telegram_user_id WHERE telegram_chat_id IS NULL"
                )
            if "referrer_user_id" not in columns:
                connection.execute("ALTER TABLE orders ADD COLUMN referrer_user_id INTEGER")
            if "referral_code" not in columns:
                connection.execute("ALTER TABLE orders ADD COLUMN referral_code TEXT")
            if "conversation_opened_at" not in columns:
                connection.execute(
                    "ALTER TABLE orders ADD COLUMN conversation_opened_at TEXT"
                )
            self._migrate_legacy_partners(connection)
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    @staticmethod
    def _migrate_legacy_partners(connection: sqlite3.Connection) -> None:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "partners" in tables:
            connection.execute(
                """
                INSERT OR IGNORE INTO referral_codes (
                    telegram_user_id, referral_code, display_name, username, created_at
                )
                SELECT telegram_user_id, referral_code, display_name, NULL, created_at
                FROM partners
                """
            )
        if "partners" in tables and "client_partner_attributions" in tables:
            connection.execute(
                """
                INSERT OR IGNORE INTO referral_attributions (
                    referred_client_user_id, referrer_user_id, referral_code, created_at
                )
                SELECT a.telegram_user_id, p.telegram_user_id, p.referral_code, a.created_at
                FROM client_partner_attributions AS a
                JOIN partners AS p ON p.id = a.partner_id
                WHERE a.telegram_user_id != p.telegram_user_id
                """
            )
        order_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(orders)").fetchall()
        }
        if "partners" in tables and "partner_id" in order_columns:
            connection.execute(
                """
                UPDATE orders
                SET referrer_user_id = (
                    SELECT p.telegram_user_id
                    FROM partners AS p
                    WHERE p.id = orders.partner_id
                )
                WHERE referrer_user_id IS NULL AND partner_id IS NOT NULL
                """
            )

    def create_order(self, order: OrderCreate) -> int:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    telegram_user_id, telegram_chat_id, username, first_name, last_name,
                    service_id, service_title, description, materials,
                    desired_deadline, budget, comment, referral_source,
                    referrer_user_id, referral_code,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                """,
                (
                    order.telegram_user_id, order.telegram_chat_id, order.username,
                    order.first_name, order.last_name, order.service_id, order.service_title,
                    order.description, order.materials, order.desired_deadline,
                    order.budget, order.comment, order.referral_source,
                    order.referrer_user_id, order.referral_code,
                    order.created_at,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def mark_notified(self, order_id: int, notified_at: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "UPDATE orders SET notified_at = ? WHERE id = ?",
                (notified_at, order_id),
            )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def update_order(self, order_id: int, order: OrderCreate) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE orders SET
                    telegram_chat_id = ?, username = ?, first_name = ?, last_name = ?, service_id = ?,
                    service_title = ?, description = ?, materials = ?,
                    desired_deadline = ?, budget = ?, comment = ?,
                    referral_source = ?, referrer_user_id = ?, referral_code = ?,
                    created_at = ?
                WHERE id = ? AND notified_at IS NULL
                """,
                (
                    order.telegram_chat_id, order.username, order.first_name, order.last_name,
                    order.service_id, order.service_title, order.description,
                    order.materials, order.desired_deadline, order.budget,
                    order.comment, order.referral_source, order.referrer_user_id,
                    order.referral_code,
                    order.created_at, order_id,
                ),
            )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_manual_source(self, telegram_user_id: int) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                """
                SELECT * FROM client_sources
                WHERE telegram_user_id = ? AND start_payload IS NULL
                """,
                (telegram_user_id,),
            ).fetchone()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def remember_manual_source(
        self,
        telegram_user_id: int,
        referral_source: str,
        *,
        created_at: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO client_sources (
                    telegram_user_id, referral_source, start_payload, created_at
                ) VALUES (?, ?, NULL, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    referral_source = excluded.referral_source,
                    start_payload = NULL,
                    created_at = excluded.created_at
                WHERE client_sources.start_payload IS NOT NULL
                """,
                (telegram_user_id, referral_source, created_at),
            )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_or_create_referral_code(
        self,
        telegram_user_id: int,
        *,
        display_name: str | None,
        username: str | None,
        created_at: str,
    ) -> sqlite3.Row:
        connection = self._connect()
        try:
            existing = connection.execute(
                "SELECT * FROM referral_codes WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE referral_codes SET display_name = ?, username = ?
                    WHERE telegram_user_id = ?
                    """,
                    (display_name, username, telegram_user_id),
                )
                connection.commit()
                return connection.execute(
                    "SELECT * FROM referral_codes WHERE telegram_user_id = ?",
                    (telegram_user_id,),
                ).fetchone()

            for _ in range(20):
                referral_code = secrets.token_hex(4)
                try:
                    connection.execute(
                        """
                        INSERT INTO referral_codes (
                            telegram_user_id, referral_code, display_name,
                            username, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            telegram_user_id, referral_code, display_name,
                            username, created_at,
                        ),
                    )
                    connection.commit()
                    return connection.execute(
                        "SELECT * FROM referral_codes WHERE telegram_user_id = ?",
                        (telegram_user_id,),
                    ).fetchone()
                except sqlite3.IntegrityError:
                    existing = connection.execute(
                        "SELECT * FROM referral_codes WHERE telegram_user_id = ?",
                        (telegram_user_id,),
                    ).fetchone()
                    if existing:
                        return existing
            raise RuntimeError("Could not generate a unique referral code")
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_referral_owner(self, referral_code: str) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                """
                SELECT * FROM referral_codes
                WHERE referral_code = ? COLLATE NOCASE
                """,
                (referral_code,),
            ).fetchone()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def bind_client_to_referrer(
        self,
        referred_client_user_id: int,
        referrer_user_id: int,
        referral_code: str,
        *,
        created_at: str,
    ) -> bool:
        if referred_client_user_id == referrer_user_id:
            return False
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO referral_attributions (
                    referred_client_user_id, referrer_user_id,
                    referral_code, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    referred_client_user_id, referrer_user_id,
                    referral_code, created_at,
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_client_referral(self, telegram_user_id: int) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                """
                SELECT
                    a.referred_client_user_id, a.referrer_user_id,
                    a.referral_code, a.created_at AS attributed_at,
                    r.display_name, r.username
                FROM referral_attributions AS a
                JOIN referral_codes AS r
                    ON r.telegram_user_id = a.referrer_user_id
                WHERE a.referred_client_user_id = ?
                """,
                (telegram_user_id,),
            ).fetchone()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def save_admin_reply_prompt(
        self,
        admin_chat_id: int,
        admin_prompt_message_id: int,
        order_id: int,
        *,
        created_at: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT OR REPLACE INTO admin_reply_prompts (
                    admin_chat_id, admin_prompt_message_id, order_id, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (admin_chat_id, admin_prompt_message_id, order_id, created_at),
            )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_order_for_admin_prompt(
        self,
        admin_chat_id: int,
        admin_prompt_message_id: int,
    ) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                """
                SELECT o.*
                FROM admin_reply_prompts AS p
                JOIN orders AS o ON o.id = p.order_id
                WHERE p.admin_chat_id = ? AND p.admin_prompt_message_id = ?
                """,
                (admin_chat_id, admin_prompt_message_id),
            ).fetchone()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def save_conversation_message(
        self,
        order_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        direction: str,
        *,
        created_at: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT OR REPLACE INTO conversation_messages (
                    order_id, telegram_chat_id, telegram_message_id,
                    direction, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    telegram_chat_id,
                    telegram_message_id,
                    direction,
                    created_at,
                ),
            )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def open_conversation_with_message(
        self,
        order_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        direction: str,
        *,
        opened_at: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT OR REPLACE INTO conversation_messages (
                    order_id, telegram_chat_id, telegram_message_id,
                    direction, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    telegram_chat_id,
                    telegram_message_id,
                    direction,
                    opened_at,
                ),
            )
            connection.execute(
                """
                UPDATE orders
                SET conversation_opened_at = COALESCE(conversation_opened_at, ?)
                WHERE id = ?
                """,
                (opened_at, order_id),
            )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_order_for_conversation_message(
        self,
        telegram_chat_id: int,
        telegram_message_id: int,
    ) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                """
                SELECT o.*
                FROM conversation_messages AS m
                JOIN orders AS o ON o.id = m.order_id
                WHERE m.telegram_chat_id = ? AND m.telegram_message_id = ?
                """,
                (telegram_chat_id, telegram_message_id),
            ).fetchone()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_open_order_for_client(
        self,
        order_id: int,
        telegram_user_id: int,
    ) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                """
                SELECT * FROM orders
                WHERE id = ? AND telegram_user_id = ?
                    AND conversation_opened_at IS NOT NULL
                """,
                (order_id, telegram_user_id),
            ).fetchone()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_open_orders_for_client(self, telegram_user_id: int) -> list[sqlite3.Row]:
        connection = self._connect()
        try:
            return connection.execute(
                """
                SELECT * FROM orders
                WHERE telegram_user_id = ? AND conversation_opened_at IS NOT NULL
                ORDER BY id DESC
                """,
                (telegram_user_id,),
            ).fetchall()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def client_has_orders(self, telegram_user_id: int) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT 1 FROM orders WHERE telegram_user_id = ? LIMIT 1",
                (telegram_user_id,),
            ).fetchone()
            return row is not None
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def save_pending_conversation_message(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        content_type: str,
        content_text: str | None,
        *,
        created_at: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT OR REPLACE INTO pending_conversation_messages (
                    telegram_user_id, telegram_chat_id, telegram_message_id,
                    content_type, content_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    telegram_chat_id,
                    telegram_message_id,
                    content_type,
                    content_text,
                    created_at,
                ),
            )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_pending_conversation_message(
        self,
        telegram_chat_id: int,
        telegram_message_id: int,
    ) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                """
                SELECT * FROM pending_conversation_messages
                WHERE telegram_chat_id = ? AND telegram_message_id = ?
                """,
                (telegram_chat_id, telegram_message_id),
            ).fetchone()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def delete_pending_conversation_message(
        self,
        telegram_chat_id: int,
        telegram_message_id: int,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                DELETE FROM pending_conversation_messages
                WHERE telegram_chat_id = ? AND telegram_message_id = ?
                """,
                (telegram_chat_id, telegram_message_id),
            )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def get_order(self, order_id: int) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def count_orders(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute("SELECT COUNT(*) AS count FROM orders").fetchone()
            return int(row["count"])
        finally:
            if str(self.path) != ":memory:":
                connection.close()
