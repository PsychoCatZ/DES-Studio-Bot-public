import re


def is_valid_referral_code(referral_code: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,60}", referral_code))
