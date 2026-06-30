"""Read-only admin statistics use case."""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository


@dataclass(frozen=True)
class AdminStatsSnapshot:
    total_users: int
    active_users: int
    banned_users: int
    trial_unused: int
    inactive_users: int
    active_subs: int
    expiring_soon: int
    income_today: int
    income_week: int
    income_month: int


class AdminStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.user_repo = UserRepository(session)
        self.sub_repo = SubscriptionRepository(session)
        self.tx_repo = TransactionRepository(session)

    async def get_snapshot(self, now: datetime.datetime | None = None) -> AdminStatsSnapshot:
        now = now or datetime.datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - datetime.timedelta(days=7)
        month_ago = now - datetime.timedelta(days=30)

        return AdminStatsSnapshot(
            total_users=await self.user_repo.count_all(),
            active_users=await self.user_repo.count_active(),
            banned_users=await self.user_repo.count_banned(),
            trial_unused=len(await self.user_repo.get_segmented_users("trial_unused")),
            inactive_users=len(await self.user_repo.get_segmented_users("inactive")),
            active_subs=await self.sub_repo.count_active(),
            expiring_soon=len(await self.sub_repo.get_expiring_soon(3)),
            income_today=await self.tx_repo.sum_income_period(today),
            income_week=await self.tx_repo.sum_income_period(week_ago),
            income_month=await self.tx_repo.sum_income_period(month_ago),
        )
