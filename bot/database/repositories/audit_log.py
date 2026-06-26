"""Audit log repository."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        admin_telegram_id: int,
        action: str,
        target_user_id: int | None = None,
        details: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            admin_telegram_id=admin_telegram_id,
            action=action,
            target_user_id=target_user_id,
            details=details,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_recent(self, limit: int = 20) -> Sequence[AuditLog]:
        result = await self.session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        return result.scalars().all()
