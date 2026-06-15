"""User CRUD operations."""

from __future__ import annotations

import datetime
import secrets
import string
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User


def _generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        language_code: str = "ru",
    ) -> User:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            user.username = username
            user.first_name = first_name
            user.last_active = datetime.datetime.utcnow()
            await self.session.commit()
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
            referral_code=_generate_referral_code(),
            last_active=datetime.datetime.utcnow(),
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def update_balance(self, telegram_id: int, amount: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        user.balance += amount
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_balance(self, telegram_id: int, balance: int) -> Optional[User]:
        await self.session.execute(
            update(User).where(User.telegram_id == telegram_id).values(balance=balance)
        )
        await self.session.commit()
        return await self.get_by_telegram_id(telegram_id)

    async def set_banned(self, telegram_id: int, is_banned: bool) -> Optional[User]:
        await self.session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(is_banned=is_banned)
        )
        await self.session.commit()
        return await self.get_by_telegram_id(telegram_id)

    async def get_all_users(
        self, offset: int = 0, limit: int = 20
    ) -> Sequence[User]:
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return result.scalars().all()

    async def search_users(self, query: str) -> Sequence[User]:
        pattern = f"%{query}%"
        result = await self.session.execute(
            select(User).where(
                (User.username.ilike(pattern))
                | (User.first_name.ilike(pattern))
                | (User.telegram_id == int(query) if query.isdigit() else False)
            )
        )
        return result.scalars().all()

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def count_active(self) -> int:
        seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        result = await self.session.execute(
            select(func.count(User.id)).where(User.last_active >= seven_days_ago)
        )
        return result.scalar_one()

    async def count_banned(self) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.is_banned.is_(True))
        )
        return result.scalar_one()

    async def get_all_telegram_ids(self) -> Sequence[int]:
        result = await self.session.execute(
            select(User.telegram_id).where(User.is_banned.is_(False))
        )
        return result.scalars().all()

    async def get_referral_count(self, telegram_id: int) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.referred_by == telegram_id)
        )
        return result.scalar_one()

    async def set_auto_renew(self, telegram_id: int, enabled: bool) -> None:
        await self.session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(auto_renew=enabled)
        )
        await self.session.commit()

    async def get_users_with_auto_renew(self) -> Sequence[User]:
        result = await self.session.execute(
            select(User).where(User.auto_renew.is_(True), User.is_banned.is_(False))
        )
        return result.scalars().all()
