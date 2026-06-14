"""Referral system logic."""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository


class ReferralService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.tx_repo = TransactionRepository(session)

    async def process_referral(
        self, new_user_telegram_id: int, referral_code: str
    ) -> bool:
        referrer = await self.user_repo.get_by_referral_code(referral_code)
        if referrer is None:
            return False

        if referrer.telegram_id == new_user_telegram_id:
            return False

        new_user = await self.user_repo.get_by_telegram_id(new_user_telegram_id)
        if new_user is None or new_user.referred_by is not None:
            return False

        new_user.referred_by = referrer.telegram_id
        await self.session.commit()

        bonus = settings.referral_bonus_stars
        if bonus > 0:
            await self.user_repo.update_balance(referrer.telegram_id, bonus)
            await self.tx_repo.create(
                user_id=referrer.telegram_id,
                tx_type="referral_bonus",
                amount=bonus,
                description=f"Referral bonus for user {new_user_telegram_id}",
            )
            logger.info(
                "Referral bonus: {} Stars to user {} for referral {}",
                bonus,
                referrer.telegram_id,
                new_user_telegram_id,
            )

        return True

    async def get_referral_stats(self, telegram_id: int) -> dict:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return {"referral_code": "", "count": 0, "earned": 0}

        count = await self.user_repo.get_referral_count(telegram_id)
        earned = count * settings.referral_bonus_stars

        return {
            "referral_code": user.referral_code or "",
            "count": count,
            "earned": earned,
        }
