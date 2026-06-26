"""Input validation utilities."""

from __future__ import annotations


def validate_topup_amount(text: str) -> int | None:
    try:
        amount = int(text.strip())
    except (ValueError, TypeError):
        return None
    if amount < 1 or amount > 100000:
        return None
    return amount


def validate_telegram_id(text: str) -> int | None:
    try:
        tid = int(text.strip())
    except (ValueError, TypeError):
        return None
    if tid <= 0:
        return None
    return tid


def validate_balance_change(text: str) -> int | None:
    try:
        amount = int(text.strip())
    except (ValueError, TypeError):
        return None
    if abs(amount) > 1_000_000:
        return None
    return amount


def validate_days(text: str) -> int | None:
    try:
        days = int(text.strip())
    except (ValueError, TypeError):
        return None
    if days < 1 or days > 3650:
        return None
    return days
