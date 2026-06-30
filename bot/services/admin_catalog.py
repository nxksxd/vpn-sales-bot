"""Read-only admin product catalog views."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories.promo_code import PromoCodeRepository
from bot.database.repositories.server_region import ServerRegionRepository


@dataclass(frozen=True)
class AdminCatalogRegionView:
    code: str
    label: str
    inbound_id: int
    server_address: str


@dataclass(frozen=True)
class AdminCatalogPromoView:
    code: str
    discount_percent: int
    usage_limit: int | None
    used_count: int


@dataclass(frozen=True)
class AdminCatalogView:
    regions: list[AdminCatalogRegionView]
    promos: list[AdminCatalogPromoView]


class AdminCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.promo_repo = PromoCodeRepository(session)
        self.region_repo = ServerRegionRepository(session)

    async def get_catalog(self) -> AdminCatalogView:
        promos = await self.promo_repo.get_all_active()
        regions = await self.region_repo.get_active_regions()
        return AdminCatalogView(
            regions=[
                AdminCatalogRegionView(
                    code=region.code,
                    label=region.label,
                    inbound_id=region.inbound_id,
                    server_address=region.server_address,
                )
                for region in regions
            ],
            promos=[
                AdminCatalogPromoView(
                    code=promo.code,
                    discount_percent=promo.discount_percent,
                    usage_limit=promo.usage_limit,
                    used_count=promo.used_count,
                )
                for promo in promos
            ],
        )
