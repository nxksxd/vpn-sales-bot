"""Tests for notification broadcast throttling/backoff."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage

from bot.services.notification import NotificationService


class FakeBot:
    def __init__(self) -> None:
        self.send_message = AsyncMock(return_value=True)


@pytest.mark.asyncio
async def test_broadcast_sleeps_between_recipients(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("bot.services.notification.asyncio.sleep", fake_sleep)

    service = NotificationService(FakeBot(), SimpleNamespace())
    sent, failed = await service.broadcast([1, 2, 3], "hello", delay_seconds=0.2)

    assert (sent, failed) == (3, 0)
    assert sleeps == [0.2, 0.2]


@pytest.mark.asyncio
async def test_broadcast_retries_after_telegram_retry_after(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("bot.services.notification.asyncio.sleep", fake_sleep)

    service = NotificationService(FakeBot(), SimpleNamespace())
    calls = 0

    async def flaky_send_custom(telegram_id, text, reply_markup=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=telegram_id, text=text),
                message="retry",
                retry_after=2,
            )
        return True

    service.send_custom = flaky_send_custom

    sent, failed = await service.broadcast([10], "hello", delay_seconds=0)

    assert (sent, failed) == (1, 0)
    assert calls == 2
    assert sleeps == [2.0]
