"""Read-only subscription data for Telegram UI."""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories.subscription import SubscriptionRepository


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


class SubscriptionViewService:
    def __init__(self, session: AsyncSession) -> None:
        self.sub_repo = SubscriptionRepository(session)

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
