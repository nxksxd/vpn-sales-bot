"""Subscription use-cases."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories.promo_code import PromoCodeRepository
from bot.database.repositories.server_region import ServerRegionRepository
from bot.services.subscription import SubscriptionService
from bot.services.xui_client import XUIClient


class SubscriptionUseCases:
    def __init__(self, session: AsyncSession, xui: XUIClient) -> None:
        self.session = session
        self.service = SubscriptionService(session, xui)
        self.promo_repo = PromoCodeRepository(session)
        self.region_repo = ServerRegionRepository(session)

    async def purchase(self, user_id: int, plan_type: str, idempotency_key: str | None = None):
        return await self.service.purchase(user_id, plan_type, idempotency_key=idempotency_key)

    async def renew(
        self,
        user_id: int,
        plan_type: str,
        transaction_description: str | None = None,
        idempotency_key: str | None = None,
    ):
        return await self.service.renew(
            user_id,
            plan_type,
            transaction_description=transaction_description,
            idempotency_key=idempotency_key,
        )

    async def resolve_region(self, region_code: str | None):
        # No explicit choice (or "auto"/"default") -> balance by current load.
        if not region_code or region_code in ("auto", "default"):
            return await self.region_repo.get_least_loaded_region()
        return await self.region_repo.get_by_code(region_code)

    async def resolve_promo(self, promo_code: str | None):
        if not promo_code:
            return None
        return await self.promo_repo.get_active_by_code(promo_code)
