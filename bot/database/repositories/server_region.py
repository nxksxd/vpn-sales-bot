"""Server region repository.

Manages the ``server_regions`` table that drives the user-facing region
picker and the inbound-routing logic on purchase. Each region is bound
to a single 3x-ui inbound (``inbound_id``) so new locations can be added
purely via the admin panel without touching code.
"""

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

    async def list_all(self) -> Sequence[ServerRegion]:
        result = await self.session.execute(
            select(ServerRegion).order_by(ServerRegion.created_at.asc())
        )
        return result.scalars().all()

    async def get_by_code(self, code: str) -> Optional[ServerRegion]:
        result = await self.session.execute(
            select(ServerRegion).where(ServerRegion.code == code, ServerRegion.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_by_code_any(self, code: str) -> Optional[ServerRegion]:
        """Get region by code regardless of active flag (admin use)."""
        result = await self.session.execute(
            select(ServerRegion).where(ServerRegion.code == code)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, region_id: int) -> Optional[ServerRegion]:
        return await self.session.get(ServerRegion, region_id)

    async def create(
        self,
        code: str,
        label: str,
        inbound_id: int,
        server_address: str = "",
    ) -> ServerRegion:
        region = ServerRegion(
            code=code,
            label=label,
            server_address=server_address,
            inbound_id=inbound_id,
            is_active=True,
        )
        self.session.add(region)
        await self.session.commit()
        await self.session.refresh(region)
        return region

    async def update(
        self,
        region_id: int,
        *,
        label: Optional[str] = None,
        inbound_id: Optional[int] = None,
        server_address: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[ServerRegion]:
        region = await self.session.get(ServerRegion, region_id)
        if region is None:
            return None
        if label is not None:
            region.label = label
        if inbound_id is not None:
            region.inbound_id = inbound_id
        if server_address is not None:
            region.server_address = server_address
        if is_active is not None:
            region.is_active = is_active
        await self.session.commit()
        await self.session.refresh(region)
        return region

    async def delete(self, region_id: int) -> bool:
        region = await self.session.get(ServerRegion, region_id)
        if region is None:
            return False
        await self.session.delete(region)
        await self.session.commit()
        return True

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
