"""User profile use cases."""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories.user import UserRepository


@dataclass(frozen=True)
class UserProfileData:
    telegram_id: int
    username: str | None
    balance: int
    auto_renew: bool
    created_at: datetime.datetime
    referral_code: str | None
    referral_count: int


class UserProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.user_repo = UserRepository(session)

    async def get_profile(self, telegram_id: int) -> UserProfileData | None:
        """Return profile data needed by Telegram UI, or None if user is missing."""
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return None

        referral_count = await self.user_repo.get_referral_count(telegram_id)
        return UserProfileData(
            telegram_id=user.telegram_id,
            username=user.username,
            balance=user.balance,
            auto_renew=user.auto_renew,
            created_at=user.created_at,
            referral_code=user.referral_code,
            referral_count=referral_count,
        )
