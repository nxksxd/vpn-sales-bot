"""Payment event repository."""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import PaymentEvent


class PaymentEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        status: str,
        amount_stars: int,
        amount_rub: int,
        charge_id: str | None = None,
        payload: str | None = None,
        error_message: str | None = None,
    ) -> PaymentEvent:
        event = PaymentEvent(
            user_id=user_id,
            status=status,
            amount_stars=amount_stars,
            amount_rub=amount_rub,
            charge_id=charge_id,
            payload=payload,
            error_message=error_message,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def update_status(
        self,
        charge_id: str,
        status: str,
        error_message: str | None = None,
    ) -> Optional[PaymentEvent]:
        event = await self.get_by_charge_id(charge_id)
        if event is None:
            return None
        event.status = status
        if error_message is not None:
            event.error_message = error_message
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def get_by_charge_id(self, charge_id: str) -> Optional[PaymentEvent]:
        result = await self.session.execute(
            select(PaymentEvent).where(PaymentEvent.charge_id == charge_id)
        )
        return result.scalar_one_or_none()

    async def get_recent(self, limit: int = 20) -> Sequence[PaymentEvent]:
        result = await self.session.execute(
            select(PaymentEvent).order_by(PaymentEvent.created_at.desc()).limit(limit)
        )
        return result.scalars().all()
