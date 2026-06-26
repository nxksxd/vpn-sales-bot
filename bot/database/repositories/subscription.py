"""Subscription CRUD operations."""

from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Subscription
from bot.domain_enums import SubscriptionStatus


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        plan_type: str,
        price_rub: int,
        days: int,
        xui_client_id: str,
        xui_inbound_id: int,
        vless_link: str,
        traffic_limit_gb: int = 0,
        is_trial: bool = False,
        sub_id: Optional[str] = None,
    ) -> Subscription:
        now = datetime.datetime.utcnow()
        sub = Subscription(
            user_id=user_id,
            plan_type=plan_type,
            price_rub=price_rub,
            status=SubscriptionStatus.ACTIVE,
            starts_at=now,
            expires_at=now + datetime.timedelta(days=days),
            xui_client_id=xui_client_id,
            xui_inbound_id=xui_inbound_id,
            sub_id=sub_id,
            vless_link=vless_link,
            traffic_limit_gb=traffic_limit_gb,
            is_trial=is_trial,
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def get_active_by_user(self, user_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            .options(selectinload(Subscription.vpn_key))
            .order_by(Subscription.expires_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, sub_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.id == sub_id)
            .options(selectinload(Subscription.vpn_key))
        )
        return result.scalar_one_or_none()

    async def get_user_subscriptions(
        self, user_id: int, limit: int = 10
    ) -> Sequence[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_expiring_soon(self, days: int) -> Sequence[Subscription]:
        now = datetime.datetime.utcnow()
        target = now + datetime.timedelta(days=days)
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= target,
                Subscription.expires_at > now,
            )
        )
        return result.scalars().all()

    async def get_expired(self) -> Sequence[Subscription]:
        now = datetime.datetime.utcnow()
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= now,
            )
        )
        return result.scalars().all()

    async def set_sub_id(self, sub_id: int, value: str) -> None:
        """Persist the 3x-ui ``subId`` for an existing subscription row."""
        await self.session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(sub_id=value)
        )
        await self.session.commit()

    async def set_status(self, sub_id: int, status: str) -> None:
        await self.session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(status=status)
        )
        await self.session.commit()

    async def extend(self, sub_id: int, days: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            return None
        base = sub.expires_at if sub.expires_at > datetime.datetime.utcnow() else datetime.datetime.utcnow()
        sub.expires_at = base + datetime.timedelta(days=days)
        sub.status = SubscriptionStatus.ACTIVE
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def mark_grace_period(self, sub_id: int) -> None:
        await self.session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(status=SubscriptionStatus.GRACE_PERIOD)
        )
        await self.session.commit()

    async def mark_suspended(self, sub_id: int) -> None:
        await self.session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(status=SubscriptionStatus.SUSPENDED)
        )
        await self.session.commit()

    async def set_expires_at(
        self, sub_id: int, expires_at: datetime.datetime
    ) -> None:
        await self.session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(expires_at=expires_at)
        )
        await self.session.commit()

    async def count_active(self) -> int:
        from sqlalchemy import func as sa_func

        result = await self.session.execute(
            select(sa_func.count(Subscription.id)).where(
                Subscription.status == SubscriptionStatus.ACTIVE
            )
        )
        return result.scalar_one()

    async def get_all_active(self) -> Sequence[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.status == SubscriptionStatus.ACTIVE)
            .options(selectinload(Subscription.vpn_key))
        )
        return result.scalars().all()
