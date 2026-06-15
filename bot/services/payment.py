"""Telegram Stars payment processing (balance stored in rubles)."""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.tx_repo = TransactionRepository(session)

    async def process_topup(
        self,
        telegram_id: int,
        amount_stars: int,
        charge_id: str,
    ) -> int:
        """Process top-up. Converts stars to rubles. Returns credited rub amount, 0 if duplicate."""
        if await self.tx_repo.charge_id_exists(charge_id):
            logger.warning(
                "Duplicate charge_id detected: {} for user {}",
                charge_id,
                telegram_id,
            )
            return 0

        rub_amount = settings.stars_to_rub(amount_stars)

        await self.tx_repo.create(
            user_id=telegram_id,
            tx_type="topup",
            amount=rub_amount,
            description=f"Пополнение: {amount_stars} Stars = {rub_amount} ₽",
            charge_id=charge_id,
        )

        await self.user_repo.update_balance(telegram_id, rub_amount)

        logger.info(
            "Balance topped up: user={} stars={} rub={} charge_id={}",
            telegram_id,
            amount_stars,
            rub_amount,
            charge_id,
        )
        return rub_amount

    async def process_refund(
        self,
        telegram_id: int,
        amount: int,
        description: str = "Refund",
    ) -> bool:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return False

        await self.tx_repo.create(
            user_id=telegram_id,
            tx_type="refund",
            amount=-amount,
            description=description,
        )

        await self.user_repo.update_balance(telegram_id, -amount)

        logger.info(
            "Refund processed: user={} amount={}",
            telegram_id,
            amount,
        )
        return True

    async def admin_adjust_balance(
        self,
        telegram_id: int,
        amount: int,
        admin_id: int,
    ) -> bool:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return False

        await self.tx_repo.create(
            user_id=telegram_id,
            tx_type="admin_adjustment",
            amount=amount,
            description=f"Корректировка админом {admin_id}: {'+' if amount >= 0 else ''}{amount} ₽",
        )

        await self.user_repo.update_balance(telegram_id, amount)

        logger.info(
            "Admin balance adjustment: user={} amount={} by_admin={}",
            telegram_id,
            amount,
            admin_id,
        )
        return True
