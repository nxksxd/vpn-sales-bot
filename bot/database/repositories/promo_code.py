"""Promo code repository.

Provides CRUD + bookkeeping for promo codes used during subscription
purchase. A code is considered *usable* when:

* ``is_active`` is True,
* ``usage_limit`` is either ``NULL`` or ``used_count < usage_limit``,
* ``valid_until`` is either ``NULL`` or in the future.

The :meth:`get_active_by_code` helper applies all three checks atomically
so callers can simply ``if promo is None: ...``.
"""

from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import PromoCode


class PromoCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_by_code(self, code: str) -> Optional[PromoCode]:
        now = datetime.datetime.utcnow()
        result = await self.session.execute(
            select(PromoCode).where(
                PromoCode.code == code,
                PromoCode.is_active.is_(True),
                or_(PromoCode.valid_until.is_(None), PromoCode.valid_until > now),
                or_(
                    PromoCode.usage_limit.is_(None),
                    PromoCode.used_count < PromoCode.usage_limit,
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[PromoCode]:
        """Return a promo code regardless of activity (admin use)."""
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.code == code)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, promo_id: int) -> Optional[PromoCode]:
        return await self.session.get(PromoCode, promo_id)

    async def get_all_active(self) -> Sequence[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.is_active.is_(True)).order_by(PromoCode.code.asc())
        )
        return result.scalars().all()

    async def list_all(self) -> Sequence[PromoCode]:
        """Return every promo code, active or not (newest first)."""
        result = await self.session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc())
        )
        return result.scalars().all()

    async def create(
        self,
        code: str,
        discount_percent: int,
        usage_limit: Optional[int] = None,
        valid_until: Optional[datetime.datetime] = None,
    ) -> PromoCode:
        promo = PromoCode(
            code=code,
            discount_percent=discount_percent,
            is_active=True,
            usage_limit=usage_limit,
            used_count=0,
            valid_until=valid_until,
        )
        self.session.add(promo)
        await self.session.commit()
        await self.session.refresh(promo)
        return promo

    async def delete(self, promo_id: int) -> bool:
        promo = await self.session.get(PromoCode, promo_id)
        if promo is None:
            return False
        await self.session.delete(promo)
        await self.session.commit()
        return True

    async def set_active(self, promo_id: int, is_active: bool) -> Optional[PromoCode]:
        promo = await self.session.get(PromoCode, promo_id)
        if promo is None:
            return None
        promo.is_active = is_active
        await self.session.commit()
        await self.session.refresh(promo)
        return promo

    async def increment_usage(self, promo_id: int) -> None:
        promo = await self.session.get(PromoCode, promo_id)
        if promo is None:
            return
        promo.used_count += 1
        if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
            promo.is_active = False
        await self.session.commit()
