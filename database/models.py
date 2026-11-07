from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrderCreate:
    telegram_user_id: int
    telegram_chat_id: int
    username: str | None
    first_name: str
    last_name: str | None
    service_id: str | None
    service_title: str
    description: str
    materials: str
    desired_deadline: str | None
    budget: str | None
    comment: str | None
    referral_source: str | None
    referrer_user_id: int | None
    referral_code: str | None
    created_at: str
