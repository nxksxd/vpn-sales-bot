"""Admin check middleware and decorator."""

from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable

from bot.config import settings


def is_admin(user_id: int) -> bool:
    return user_id == settings.admin_telegram_id


def admin_only(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(handler)
    async def wrapper(event: Any, *args: Any, **kwargs: Any) -> Any:
        user = getattr(event, "from_user", None)
        uid = getattr(user, "id", None) if user else None
        if uid is None or not is_admin(uid):
            try:
                if hasattr(event, "data") and hasattr(event, "answer"):
                    await event.answer("Нет доступа.", show_alert=True)
                elif hasattr(event, "answer"):
                    await event.answer("\U0001f6ab Нет доступа.")
            except Exception:
                pass
            return None
        return await handler(event, *args, **kwargs)

    return wrapper
