"""Telegram Stars payment processing."""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

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
        amount: int,
        charge_id: str,
    ) -> bool:
        if await self.tx_repo.charge_id_exists(charge_id):
            logger.warning(
                "Duplicate charge_id detected: {} for user {}",
                charge_id,
                telegram_id,
            )
            return False

        await self.tx_repo.create(
            user_id=telegram_id,
            tx_type="topup",
            amount=amount,
            description=f"Top-up {amount} Stars",
            charge_id=charge_id,
        )

        await self.user_repo.update_balance(telegram_id, amount)

        logger.info(
            "Balance topped up: user={} amount={} charge_id={}",
            telegram_id,
            amount,
            charge_id,
        )
        return True

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
            description=f"Admin adjustment by {admin_id}: {'+' if amount >= 0 else ''}{amount} Stars",
        )

        await self.user_repo.update_balance(telegram_id, amount)

        logger.info(
            "Admin balance adjustment: user={} amount={} by_admin={}",
            telegram_id,
            amount,
            admin_id,
        )
        return True
