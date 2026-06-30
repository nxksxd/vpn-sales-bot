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
    GC_INTERVAL_SECONDS: int = 300

    def __init__(self) -> None:
        self._events: Dict[int, Deque[float]] = defaultdict(deque)
        self._cooldown_until: Dict[int, float] = {}
        self._last_gc: float = 0.0

    def _gc(self, now: float) -> None:
        """Drop idle users so long-running bot processes do not leak IDs forever."""
        if now - self._last_gc < self.GC_INTERVAL_SECONDS:
            return

        cutoff = now - 60.0
        for user_id, events in list(self._events.items()):
            while events and events[0] < cutoff:
                events.popleft()
            if not events:
                self._events.pop(user_id, None)

        for user_id, cooldown_end in list(self._cooldown_until.items()):
            if cooldown_end <= now:
                self._cooldown_until.pop(user_id, None)

        self._last_gc = now

    def _check(self, user_id: int) -> Tuple[bool, float]:
        now = time.monotonic()
        self._gc(now)

        cooldown_end = self._cooldown_until.get(user_id, 0.0)
        if cooldown_end and now >= cooldown_end:
            self._cooldown_until.pop(user_id, None)
            cooldown_end = 0.0
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
