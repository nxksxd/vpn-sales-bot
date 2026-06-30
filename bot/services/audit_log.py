"""Admin audit logging service."""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.repositories.audit_log import AuditLogRepository


@dataclass(frozen=True)
class AuditLogView:
    admin_telegram_id: int
    action: str
    target_user_id: int | None
    created_at: datetime.datetime


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

    async def get_recent_page(self, *, page: int, limit: int) -> list[AuditLogView]:
        offset = max(0, page) * limit
        logs = await self.repo.get_recent(limit=limit + offset)
        return [
            AuditLogView(
                admin_telegram_id=log.admin_telegram_id,
                action=log.action,
                target_user_id=log.target_user_id,
                created_at=log.created_at,
            )
            for log in list(logs)[offset : offset + limit]
        ]
