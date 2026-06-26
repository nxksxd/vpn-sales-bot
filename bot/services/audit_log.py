"""Admin audit logging service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories.audit_log import AuditLogRepository


class AuditLogService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AuditLogRepository(session)

    async def log(
        self,
        admin_telegram_id: int,
        action: str,
        target_user_id: int | None = None,
        details: str | None = None,
    ) -> None:
        await self.repo.create(
            admin_telegram_id=admin_telegram_id,
            action=action,
            target_user_id=target_user_id,
            details=details,
        )
