"""Read-only subscription data for Telegram UI."""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories.server_region import ServerRegionRepository
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.user import UserRepository


@dataclass(frozen=True)
class RegionOptionView:
    code: str
    label: str


@dataclass(frozen=True)
class ActiveSubscriptionView:
    plan_type: str
    status: str
    expires_at: datetime.datetime
    traffic_limit_gb: int
    sub_id: str | None
    subscription_url: str | None
    vless_link: str | None

    @property
    def is_legacy(self) -> bool:
        return not self.sub_id


@dataclass(frozen=True)
class SubscriptionMenuView:
    active: ActiveSubscriptionView | None
    trial_used: bool


@dataclass(frozen=True)
class SubscriptionHistoryItemView:
    plan_type: str
    status: str
    starts_at: datetime.datetime
    expires_at: datetime.datetime


class SubscriptionViewService:
    def __init__(self, session: AsyncSession) -> None:
        self.sub_repo = SubscriptionRepository(session)
        self.user_repo = UserRepository(session)
        self.region_repo = ServerRegionRepository(session)

    async def get_active_regions(self) -> list[RegionOptionView]:
        regions = await self.region_repo.get_active_regions()
        return [RegionOptionView(code=region.code, label=region.label) for region in regions]

    async def get_active_subscription(
        self, telegram_id: int
    ) -> ActiveSubscriptionView | None:
        """Return active subscription data needed by menu UI, or None."""
        active = await self.sub_repo.get_active_by_user(telegram_id)
        if active is None:
            return None

        return ActiveSubscriptionView(
            plan_type=active.plan_type,
            status=active.status,
            expires_at=active.expires_at,
            traffic_limit_gb=active.traffic_limit_gb,
            sub_id=active.sub_id,
            subscription_url=settings.subscription_url(active.sub_id),
            vless_link=active.vless_link,
        )

    async def get_subscription_menu(self, telegram_id: int) -> SubscriptionMenuView:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        return SubscriptionMenuView(
            active=await self.get_active_subscription(telegram_id),
            trial_used=bool(user and user.trial_used),
        )

    async def get_subscription_history(
        self,
        telegram_id: int,
        *,
        limit: int = 10,
    ) -> list[SubscriptionHistoryItemView]:
        subs = await self.sub_repo.get_user_subscriptions(telegram_id, limit=limit)
        return [
            SubscriptionHistoryItemView(
                plan_type=sub.plan_type,
                status=sub.status,
                starts_at=sub.starts_at,
                expires_at=sub.expires_at,
            )
            for sub in subs
        ]
