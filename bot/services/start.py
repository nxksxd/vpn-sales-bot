"""Start command use cases."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories.user import UserRepository
from bot.services.referral import ReferralService


@dataclass(frozen=True)
class ReferralNotification:
    referrer_telegram_id: int
    bonus_rub: int
    balance: int


@dataclass(frozen=True)
class StartResult:
    show_onboarding: bool
    referral_notification: ReferralNotification | None = None


class StartService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.referral = ReferralService(session)

    async def process_start(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        language_code: str,
        text: str,
    ) -> StartResult:
        """Create/update user, process referral payload, and persist onboarding state."""
        user = await self.user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
        )
        show_onboarding = not user.onboarding_completed

        referral_notification: ReferralNotification | None = None
        referral_code = self._extract_referral_code(text)
        if referral_code:
            processed = await self.referral.process_referral(telegram_id, referral_code)
            if processed:
                referrer = await self.user_repo.get_by_referral_code(referral_code)
                if referrer is not None:
                    referral_notification = ReferralNotification(
                        referrer_telegram_id=referrer.telegram_id,
                        bonus_rub=settings.referral_bonus_rub,
                        balance=referrer.balance,
                    )

        if show_onboarding:
            user.onboarding_completed = True
            await self.session.commit()

        return StartResult(
            show_onboarding=show_onboarding,
            referral_notification=referral_notification,
        )

    @staticmethod
    def _extract_referral_code(text: str) -> str | None:
        if not text.startswith("/start ref_"):
            return None
        code = text.split("ref_", 1)[1].strip()
        return code or None
