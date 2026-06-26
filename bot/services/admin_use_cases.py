"""Admin-facing use-cases."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.domain_enums import AuditAction
from bot.services.audit_log import AuditLogService
from bot.services.payment import PaymentService
from bot.database.repositories.user import UserRepository


class AdminUseCases:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.payment = PaymentService(session)
        self.users = UserRepository(session)
        self.audit = AuditLogService(session)

    async def adjust_user_balance(self, admin_id: int, user_id: int, amount: int) -> bool:
        ok = await self.payment.admin_adjust_balance(user_id, amount, admin_id)
        if ok:
            await self.audit.log(
                admin_id,
                AuditAction.USER_BALANCE_CHANGED,
                target_user_id=user_id,
                details=f"amount={amount}",
            )
        return ok

    async def toggle_ban(self, admin_id: int, user_id: int, is_banned: bool) -> None:
        await self.users.set_banned(user_id, is_banned)
        await self.audit.log(
            admin_id,
            AuditAction.USER_BANNED if is_banned else AuditAction.USER_UNBANNED,
            target_user_id=user_id,
            details=f"is_banned={is_banned}",
        )
