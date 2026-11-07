from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    admin_chat_id: int
    database_path: Path
    timezone: ZoneInfo

    @classmethod
    def from_env(cls, *, require_secrets: bool = True) -> "Config":
        load_dotenv(BASE_DIR / ".env")
        token = os.getenv("BOT_TOKEN", "").strip()
        admin_raw = os.getenv("ADMIN_CHAT_ID", "").strip()

        if require_secrets and not token:
            raise ValueError("BOT_TOKEN is not set in .env")
        if require_secrets and not admin_raw:
            raise ValueError("ADMIN_CHAT_ID is not set in .env")

        try:
            admin_chat_id = int(admin_raw) if admin_raw else 0
        except ValueError as exc:
            raise ValueError("ADMIN_CHAT_ID must be an integer") from exc

        database_raw = os.getenv("DATABASE_PATH", "data/orders.db").strip()
        database_path = Path(database_raw)
        if not database_path.is_absolute():
            database_path = BASE_DIR / database_path

        timezone_name = os.getenv("APP_TIMEZONE", "Asia/Krasnoyarsk").strip()
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown APP_TIMEZONE: {timezone_name}") from exc

        return cls(token, admin_chat_id, database_path, timezone)
