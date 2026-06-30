from dataclasses import dataclass
from typing import Any, cast

import pytest

from bot.services import start as start_module
from bot.services.start import StartService


@dataclass
class _User:
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    language_code: str = "ru"
    onboarding_completed: bool = False
    referred_by: int | None = None
    balance: int = 0


class _Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def test_extract_referral_code() -> None:
    assert StartService._extract_referral_code("/start ref_ABC123") == "ABC123"
    assert StartService._extract_referral_code("/start ref_   ") is None
    assert StartService._extract_referral_code("/start") is None


@pytest.mark.asyncio
async def test_process_start_marks_onboarding_once(monkeypatch) -> None:
    session = _Session()
    user = _User(telegram_id=10, onboarding_completed=False)

    class FakeUserRepository:
        def __init__(self, session_arg: _Session) -> None:
            assert session_arg is session

        async def get_or_create(self, **kwargs) -> _User:
            assert kwargs["telegram_id"] == 10
            assert kwargs["username"] == "neo"
            return user

        async def get_by_referral_code(self, code: str) -> _User | None:
            raise AssertionError("referrer lookup should not run without referral code")

    class FakeReferralService:
        def __init__(self, session_arg: _Session) -> None:
            assert session_arg is session

        async def process_referral(self, telegram_id: int, referral_code: str) -> bool:
            raise AssertionError("referral processing should not run without referral code")

    monkeypatch.setattr(start_module, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(start_module, "ReferralService", FakeReferralService)

    result = await StartService(cast(Any, session)).process_start(
        telegram_id=10,
        username="neo",
        first_name="Neo",
        language_code="ru",
        text="/start",
    )

    assert result.show_onboarding is True
    assert result.referral_notification is None
    assert user.onboarding_completed is True
    assert session.commits == 1


@pytest.mark.asyncio
async def test_process_start_returns_referral_notification(monkeypatch) -> None:
    session = _Session()
    user = _User(telegram_id=20, onboarding_completed=True)
    referrer = _User(telegram_id=99, balance=150)

    class FakeUserRepository:
        def __init__(self, session_arg: _Session) -> None:
            assert session_arg is session

        async def get_or_create(self, **kwargs) -> _User:
            return user

        async def get_by_referral_code(self, code: str) -> _User | None:
            assert code == "REF123"
            return referrer

    class FakeReferralService:
        def __init__(self, session_arg: _Session) -> None:
            assert session_arg is session

        async def process_referral(self, telegram_id: int, referral_code: str) -> bool:
            assert telegram_id == 20
            assert referral_code == "REF123"
            return True

    monkeypatch.setattr(start_module, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(start_module, "ReferralService", FakeReferralService)

    result = await StartService(cast(Any, session)).process_start(
        telegram_id=20,
        username=None,
        first_name=None,
        language_code="ru",
        text="/start ref_REF123",
    )

    assert result.show_onboarding is False
    assert result.referral_notification is not None
    assert result.referral_notification.referrer_telegram_id == 99
    assert result.referral_notification.balance == 150
    assert session.commits == 0
