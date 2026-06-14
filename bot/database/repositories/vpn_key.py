"""VPN key CRUD operations."""

from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import VpnKey


class VpnKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        subscription_id: int,
        user_id: int,
        xui_client_id: str,
        xui_inbound_id: int,
        email: str,
        vless_link: str,
    ) -> VpnKey:
        key = VpnKey(
            subscription_id=subscription_id,
            user_id=user_id,
            xui_client_id=xui_client_id,
            xui_inbound_id=xui_inbound_id,
            email=email,
            vless_link=vless_link,
            is_active=True,
        )
        self.session.add(key)
        await self.session.commit()
        await self.session.refresh(key)
        return key

    async def get_by_client_id(self, xui_client_id: str) -> Optional[VpnKey]:
        result = await self.session.execute(
            select(VpnKey).where(VpnKey.xui_client_id == xui_client_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_user(self, user_id: int) -> Optional[VpnKey]:
        result = await self.session.execute(
            select(VpnKey)
            .where(VpnKey.user_id == user_id, VpnKey.is_active.is_(True))
            .order_by(VpnKey.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_user_keys(self, user_id: int) -> Sequence[VpnKey]:
        result = await self.session.execute(
            select(VpnKey)
            .where(VpnKey.user_id == user_id)
            .order_by(VpnKey.created_at.desc())
        )
        return result.scalars().all()

    async def set_active(self, key_id: int, is_active: bool) -> None:
        await self.session.execute(
            update(VpnKey)
            .where(VpnKey.id == key_id)
            .values(is_active=is_active, updated_at=datetime.datetime.utcnow())
        )
        await self.session.commit()

    async def update_vless_link(
        self, key_id: int, vless_link: str, xui_client_id: str
    ) -> None:
        await self.session.execute(
            update(VpnKey)
            .where(VpnKey.id == key_id)
            .values(
                vless_link=vless_link,
                xui_client_id=xui_client_id,
                updated_at=datetime.datetime.utcnow(),
            )
        )
        await self.session.commit()

    async def deactivate_by_subscription(self, subscription_id: int) -> None:
        await self.session.execute(
            update(VpnKey)
            .where(VpnKey.subscription_id == subscription_id)
            .values(is_active=False, updated_at=datetime.datetime.utcnow())
        )
        await self.session.commit()
