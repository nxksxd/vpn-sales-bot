"""Promo code repository."""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import PromoCode


class PromoCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_by_code(self, code: str) -> Optional[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.code == code, PromoCode.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_all_active(self) -> Sequence[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.is_active.is_(True)).order_by(PromoCode.code.asc())
        )
        return result.scalars().all()

    async def increment_usage(self, promo_id: int) -> None:
        promo = await self.session.get(PromoCode, promo_id)
        if promo is None:
            return
        promo.used_count += 1
        if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
            promo.is_active = False
        await self.session.commit()
