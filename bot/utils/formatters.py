"""Text formatting utilities."""

from __future__ import annotations

import datetime
import html
from typing import Any, Optional


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def code(value: Any) -> str:
    return f"<code>{esc(value)}</code>"


def fmt_date(dt: Optional[datetime.datetime]) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def fmt_stars(amount: int) -> str:
    return f"{amount} \u2b50"


def fmt_bytes(b: Optional[int]) -> str:
    if b is None or b == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(b)
    for unit in units:
        if abs(val) < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} PB"


def fmt_traffic_limit(gb: int) -> str:
    if gb <= 0:
        return "\u221e (безлимит)"
    return f"{gb} GB"


def fmt_status(status: str) -> str:
    mapping = {
        "active": "\u2705 Активна",
        "expired": "\u274c Истекла",
        "cancelled": "\U0001f6ab Отменена",
    }
    return mapping.get(status, status)


def fmt_plan(plan_type: str) -> str:
    mapping = {
        "1m": "1 месяц",
        "3m": "3 месяца",
        "6m": "6 месяцев",
        "12m": "12 месяцев",
    }
    return mapping.get(plan_type, plan_type)


def pluralize_days(n: int) -> str:
    abs_n = abs(n)
    if abs_n % 10 == 1 and abs_n % 100 != 11:
        return f"{n} день"
    if 2 <= abs_n % 10 <= 4 and not (12 <= abs_n % 100 <= 14):
        return f"{n} дня"
    return f"{n} дней"


def days_until(dt: Optional[datetime.datetime]) -> int:
    if dt is None:
        return 0
    delta = dt - datetime.datetime.utcnow()
    return max(0, delta.days)
