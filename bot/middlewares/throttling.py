"""Rate limiting middleware — per-user request throttling."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable, Deque, Dict, Tuple

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import settings


class ThrottlingMiddleware(BaseMiddleware):
    PER_MINUTE: int = settings.rate_limit_per_minute
    COOLDOWN_SECONDS: int = 60

    def __init__(self) -> None:
        self._events: Dict[int, Deque[float]] = defaultdict(deque)
        self._cooldown_until: Dict[int, float] = {}

    def _check(self, user_id: int) -> Tuple[bool, float]:
        now = time.monotonic()

        cooldown_end = self._cooldown_until.get(user_id, 0.0)
        if now < cooldown_end:
            return False, cooldown_end - now

        events = self._events[user_id]
        cutoff = now - 60.0
        while events and events[0] < cutoff:
            events.popleft()

        if len(events) >= self.PER_MINUTE:
            self._cooldown_until[user_id] = now + self.COOLDOWN_SECONDS
            return False, float(self.COOLDOWN_SECONDS)

        events.append(now)
        return True, 0.0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        uid = getattr(user, "id", None) if user else None
        if uid is None:
            return await handler(event, data)

        allowed, retry_after = self._check(uid)
        if allowed:
            return await handler(event, data)

        wait = f"{int(retry_after)}s"
        try:
            if hasattr(event, "data"):
                await event.answer(
                    f"Слишком много запросов. Попробуйте через {wait}.",
                    show_alert=True,
                )
            elif hasattr(event, "answer"):
                await event.answer(
                    f"\u23f1 Слишком много запросов. Попробуйте через {wait}."
                )
        except Exception:
            pass
        return None
