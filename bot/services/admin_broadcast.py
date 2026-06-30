"""Admin broadcast audience selection."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.user import UserRepository
from bot.domain_enums import AuditAction
from bot.services.audit_log import AuditLogService


class AdminBroadcastService:
    def __init__(self, session: AsyncSession) -> None:
        self.user_repo = UserRepository(session)
        self.sub_repo = SubscriptionRepository(session)

    async def get_target_telegram_ids(self, target: str) -> list[int]:
        if target == "adm:bc_all":
            return list(await self.user_repo.get_all_telegram_ids())
        if target == "adm:bc_active":
            active_subs = await self.sub_repo.get_all_active()
            return [sub.user_id for sub in active_subs]
        if target == "adm:bc_expiring":
            expiring = await self.sub_repo.get_expiring_soon(3)
            return [sub.user_id for sub in expiring]
        if target == "adm:bc_new":
            return list(await self.user_repo.get_segmented_users("new_users"))
        if target == "adm:bc_trial":
            return list(await self.user_repo.get_segmented_users("trial_unused"))
        if target == "adm:bc_inactive":
            return list(await self.user_repo.get_segmented_users("inactive"))
        return []

    async def log_broadcast_sent(
        self,
        *,
        admin_id: int,
        target: str,
        sent: int,
        failed: int,
    ) -> None:
        await AuditLogService(self.user_repo.session).log(
            admin_telegram_id=admin_id,
            action=AuditAction.BROADCAST_SENT,
            details=f"target={target} sent={sent} failed={failed}",
        )
