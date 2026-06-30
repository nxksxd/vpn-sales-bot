"""Admin VPN key read operations."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import Subscription
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.vpn_key import VpnKeyRepository
from bot.domain_enums import AuditAction
from bot.services.audit_log import AuditLogService
from bot.services.subscription import SubscriptionService
from bot.services.xui_client import XUIClient


@dataclass(frozen=True)
class AdminKeyView:
    xui_client_id: str
    email: str
    xui_inbound_id: int
    is_active: bool


@dataclass(frozen=True)
class AdminTrafficResetTarget:
    inbound_id: int
    email: str


class AdminKeyService:
    def __init__(self, session: AsyncSession) -> None:
        self.sub_repo = SubscriptionRepository(session)
        self.key_repo = VpnKeyRepository(session)

    async def get_user_key_views(self, telegram_id: int) -> list[AdminKeyView]:
        keys = await self.key_repo.get_user_keys(telegram_id)
        return [
            AdminKeyView(
                xui_client_id=key.xui_client_id,
                email=key.email,
                xui_inbound_id=key.xui_inbound_id,
                is_active=key.is_active,
            )
            for key in keys
        ]

    async def get_active_subscription(self, telegram_id: int) -> Subscription | None:
        return await self.sub_repo.get_active_by_user(telegram_id)

    async def get_latest_subscription(self, telegram_id: int) -> Subscription | None:
        active = await self.sub_repo.get_active_by_user(telegram_id)
        if active is not None:
            return active
        subs = await self.sub_repo.get_user_subscriptions(telegram_id, limit=1)
        return subs[0] if subs else None

    async def mark_subscription_active(self, subscription_id: int) -> None:
        from bot.domain_enums import SubscriptionStatus

        await self.sub_repo.set_status(subscription_id, SubscriptionStatus.ACTIVE)

    async def extend_subscription(self, *, admin_id: int, telegram_id: int, days: int) -> bool:
        active = await self.sub_repo.get_active_by_user(telegram_id)
        if active is None:
            return False

        xui = XUIClient()
        try:
            sub = await self.sub_repo.extend(active.id, days)

            if sub and sub.xui_client_id:
                new_expiry_ms = int(sub.expires_at.timestamp() * 1000)
                key = await self.key_repo.get_by_client_id(sub.xui_client_id)
                email = key.email if key else f"user_{telegram_id}"
                try:
                    await xui.update_client(
                        sub.xui_inbound_id or settings.xui_inbound_id,
                        sub.xui_client_id,
                        {
                            "id": sub.xui_client_id,
                            "email": email,
                            "enable": True,
                            "expiryTime": new_expiry_ms,
                        },
                    )
                except Exception as e:
                    logger.error("Failed to update 3X-UI expiry: {}", e)
        finally:
            await xui.close()

        await AuditLogService(self.sub_repo.session).log(
            admin_telegram_id=admin_id,
            action=AuditAction.SUBSCRIPTION_EXTENDED,
            target_user_id=telegram_id,
            details=f"+{days}d",
        )
        return True

    async def cancel_subscription(self, *, admin_id: int, telegram_id: int) -> bool:
        active = await self.sub_repo.get_active_by_user(telegram_id)
        if active is None:
            return False

        xui = XUIClient()
        try:
            await SubscriptionService(self.sub_repo.session, xui).deactivate(active)
        finally:
            await xui.close()

        await AuditLogService(self.sub_repo.session).log(
            admin_telegram_id=admin_id,
            action=AuditAction.SUBSCRIPTION_CANCELLED,
            target_user_id=telegram_id,
        )
        return True

    async def get_traffic_reset_target(
        self,
        telegram_id: int,
    ) -> AdminTrafficResetTarget | None:
        key = await self.key_repo.get_active_by_user(telegram_id)
        if key is None:
            return None
        return AdminTrafficResetTarget(
            inbound_id=key.xui_inbound_id,
            email=key.email,
        )
