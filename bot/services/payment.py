"""Telegram Stars payment processing (balance stored in rubles)."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import PaymentEvent, User
from bot.database.repositories.payment_event import PaymentEventRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.domain_enums import PaymentStatus, TransactionType


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.event_repo = PaymentEventRepository(session)

    async def validate_telegram_topup_allowed(self, telegram_id: int) -> str | None:
        """Return a user-facing pre-checkout error, or None when top-up is allowed."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return "Пользователь не зарегистрирован. Отправьте /start."
        if user.is_banned:
            return "Ваш аккаунт заблокирован."
        return None

    async def get_user_balance_or_default(
        self, telegram_id: int, default_balance: int
    ) -> int:
        """Return current user balance, or a fallback when user row is unavailable."""
        result = await self.session.execute(
            select(User.balance).where(User.telegram_id == telegram_id)
        )
        balance = result.scalar_one_or_none()
        return default_balance if balance is None else balance

    async def get_user_balance(self, telegram_id: int) -> int | None:
        """Return current user balance in rubles, or None when user is missing."""
        result = await self.session.execute(
            select(User.balance).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def record_yookassa_pending_topup(
        self,
        *,
        telegram_id: int,
        amount_rub: int,
        payment_id: str,
    ) -> None:
        """Persist a pending YooKassa top-up event once per payment id."""
        existing_event = await self.event_repo.get_by_charge_id(payment_id)
        if existing_event is not None:
            return

        await self.event_repo.create(
            user_id=telegram_id,
            status=PaymentStatus.PENDING,
            amount_stars=0,
            amount_rub=amount_rub,
            charge_id=payment_id,
            payload=f"yookassa:topup:{amount_rub}",
        )

    async def process_topup(
        self,
        telegram_id: int,
        amount_stars: int,
        charge_id: str,
    ) -> int:
        """Process top-up atomically. Returns credited rub amount, 0 if duplicate."""
        rub_amount = settings.stars_to_rub(amount_stars)
        rate_snapshot = str(settings.stars_to_rub_rate)

        try:
            async with self.session.begin():
                result = await self.session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    raise ValueError("User not found")

                await self.tx_repo.create(
                    user_id=telegram_id,
                    tx_type=TransactionType.TOPUP,
                    amount_rub=rub_amount,
                    amount_stars=amount_stars,
                    description=f"Пополнение: {amount_stars} Stars = {rub_amount} ₽",
                    charge_id=charge_id,
                    idempotency_key=f"topup:{charge_id}",
                    rate_snapshot=rate_snapshot,
                    commit=False,
                )
                user.balance += rub_amount
        except IntegrityError:
            await self.session.rollback()
            logger.warning(
                "Duplicate charge_id detected: {} for user {}",
                charge_id,
                telegram_id,
            )
            return 0

        logger.info(
            "Balance topped up: user={} stars={} rub={} charge_id={}",
            telegram_id,
            amount_stars,
            rub_amount,
            charge_id,
        )
        return rub_amount

    async def process_telegram_successful_topup(
        self,
        telegram_id: int,
        amount_stars: int,
        charge_id: str,
        payload: str,
    ) -> int:
        """Record a Telegram Stars payment event and credit balance once.

        Returns credited rubles, or 0 when the charge was already processed.
        The event insert, transaction insert, and balance credit are owned by
        the service layer so handlers do not duplicate payment persistence
        logic or split it across several commits.
        """
        rub_amount = settings.stars_to_rub(amount_stars)
        rate_snapshot = str(settings.stars_to_rub_rate)

        try:
            async with self.session.begin():
                result = await self.session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    raise ValueError("User not found")

                self.session.add(
                    PaymentEvent(
                        user_id=telegram_id,
                        status=PaymentStatus.PAID,
                        amount_stars=amount_stars,
                        amount_rub=rub_amount,
                        charge_id=charge_id,
                        payload=payload,
                    )
                )
                await self.tx_repo.create(
                    user_id=telegram_id,
                    tx_type=TransactionType.TOPUP,
                    amount_rub=rub_amount,
                    amount_stars=amount_stars,
                    description=f"Пополнение: {amount_stars} Stars = {rub_amount} ₽",
                    charge_id=charge_id,
                    idempotency_key=f"topup:{charge_id}",
                    rate_snapshot=rate_snapshot,
                    commit=False,
                )
                user.balance += rub_amount
        except IntegrityError:
            await self.session.rollback()
            logger.warning(
                "Duplicate Telegram payment detected: {} for user {}",
                charge_id,
                telegram_id,
            )
            return 0

        logger.info(
            "Telegram Stars top-up processed: user={} stars={} rub={} charge_id={}",
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
        description: str = "Balance debit adjustment",
        charge_id: str | None = None,
    ) -> bool:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return False

        await self.tx_repo.create(
            user_id=telegram_id,
            tx_type=TransactionType.BALANCE_DEBIT_ADJUSTMENT,
            amount_rub=-amount,
            description=description,
            rate_snapshot=str(settings.stars_to_rub_rate),
        )

        await self.user_repo.update_balance(telegram_id, -amount)

        # Tie the refund to its payment event so its lifecycle ends in REFUNDED.
        if charge_id is not None:
            await self.event_repo.update_status(
                charge_id,
                PaymentStatus.REFUNDED,
                error_message=description,
            )

        logger.info(
            "Balance debit adjustment processed: user={} amount={} charge_id={}",
            telegram_id,
            amount,
            charge_id,
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
            tx_type=TransactionType.ADMIN_ADJUSTMENT,
            amount_rub=amount,
            description=f"Корректировка админом {admin_id}: {'+' if amount >= 0 else ''}{amount} ₽",
            rate_snapshot=str(settings.stars_to_rub_rate),
        )

        await self.user_repo.update_balance(telegram_id, amount)

        logger.info(
            "Admin balance adjustment: user={} amount={} by_admin={}",
            telegram_id,
            amount,
            admin_id,
        )
        return True
