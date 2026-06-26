"""Server region repository."""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import ServerRegion, Subscription
from bot.domain_enums import SubscriptionStatus


class ServerRegionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_regions(self) -> Sequence[ServerRegion]:
        result = await self.session.execute(
            select(ServerRegion).where(ServerRegion.is_active.is_(True)).order_by(ServerRegion.label.asc())
        )
        return result.scalars().all()

    async def get_by_code(self, code: str) -> Optional[ServerRegion]:
        result = await self.session.execute(
            select(ServerRegion).where(ServerRegion.code == code, ServerRegion.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_least_loaded_region(self) -> Optional[ServerRegion]:
        """Pick the active region with the fewest active subscriptions."""
        regions = await self.get_active_regions()
        if not regions:
            return None
        rows = await self.session.execute(
            select(Subscription.region_code, func.count(Subscription.id))
            .where(Subscription.status == SubscriptionStatus.ACTIVE)
            .group_by(Subscription.region_code)
        )
        load = {code: count for code, count in rows.all()}
        return min(regions, key=lambda r: load.get(r.code, 0))
