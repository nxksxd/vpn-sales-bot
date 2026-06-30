"""Regression tests for FSM reset/cancel behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.config import settings
from bot.handlers.admin import broadcast as admin_broadcast
from bot.handlers.admin import users as admin_users


class FakeState:
    def __init__(self, data: dict | None = None) -> None:
        self.data = data or {}
        self.cleared = False

    async def get_data(self) -> dict:
        return self.data

    async def clear(self) -> None:
        self.cleared = True


class FakeMessage:
    def __init__(self, text: str, user_id: int = 1) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.answers: list[tuple[str, dict]] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append((text, kwargs))


@pytest.fixture(autouse=True)
def admin_user(monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_telegram_id", 1)


@pytest.mark.asyncio
async def test_balance_change_keeps_state_on_invalid_amount() -> None:
    state = FakeState({"target_user": 42})
    message = FakeMessage("not-a-number")

    await admin_users.msg_balance_change(message, state)

    assert state.cleared is False
    assert message.answers
    assert "Некорректная сумма" in message.answers[0][0]


@pytest.mark.asyncio
async def test_user_search_keeps_state_on_empty_query() -> None:
    state = FakeState()
    message = FakeMessage("   ")

    await admin_users.msg_user_search(message, state)

    assert state.cleared is False
    assert message.answers
    assert "Пустой запрос" in message.answers[0][0]


@pytest.mark.asyncio
async def test_user_message_keeps_state_on_empty_text() -> None:
    state = FakeState({"target_user": 42})
    message = FakeMessage("   ")

    await admin_users.msg_send_user_message(message, bot=SimpleNamespace(), state=state)

    assert state.cleared is False
    assert message.answers
    assert "Пустое сообщение" in message.answers[0][0]


@pytest.mark.asyncio
async def test_broadcast_keeps_state_on_empty_text() -> None:
    state = FakeState({"broadcast_target": "adm:bc_all"})
    message = FakeMessage("   ")

    await admin_broadcast.msg_broadcast_text(message, bot=SimpleNamespace(), state=state)

    assert state.cleared is False
    assert message.answers
    assert "Пустое сообщение" in message.answers[0][0]
