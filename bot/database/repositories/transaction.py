"""Transaction CRUD operations."""

from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Transaction
from bot.domain_enums import TransactionType


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        tx_type: str,
        amount_rub: int,
        amount_stars: Optional[int] = None,
        description: Optional[str] = None,
        charge_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        rate_snapshot: Optional[str] = None,
        commit: bool = True,
    ) -> Transaction:
        tx = Transaction(
            user_id=user_id,
            type=tx_type,
            amount_rub=amount_rub,
            amount_stars=amount_stars,
            rate_snapshot=rate_snapshot,
            idempotency_key=idempotency_key,
            description=description,
            stars_payment_charge_id=charge_id,
        )
        self.session.add(tx)
        if commit:
            await self.session.commit()
            await self.session.refresh(tx)
        return tx

    async def charge_id_exists(self, charge_id: str) -> bool:
        result = await self.session.execute(
            select(Transaction.id).where(
                Transaction.stars_payment_charge_id == charge_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(
                Transaction.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none()

    async def get_user_history(
        self, user_id: int, limit: int = 20
    ) -> Sequence[Transaction]:
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def sum_by_type_since(
        self, tx_type: str, since: datetime.datetime
    ) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(
                Transaction.type == tx_type,
                Transaction.created_at >= since,
            )
        )
        return result.scalar_one()

    async def sum_income_period(
        self, since: datetime.datetime
    ) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(
                Transaction.type == TransactionType.TOPUP,
                Transaction.created_at >= since,
            )
        )
        return result.scalar_one()

    async def count_since(self, since: datetime.datetime) -> int:
        result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.created_at >= since
            )
        )
        return result.scalar_one()
