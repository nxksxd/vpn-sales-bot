"""User CRUD operations."""

from __future__ import annotations

import datetime
import secrets
import string
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
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
        # Fast path: user already exists.
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            user.username = username
            user.first_name = first_name
            user.last_active = datetime.datetime.utcnow()
            # Revive a previously soft-deleted account on re-engagement.
            user.deleted_at = None
            await self.session.commit()
            return user

        # Race-safe insert: if a concurrent request already created the user,
        # ON CONFLICT DO NOTHING avoids a UniqueViolationError that would
        # otherwise abort the whole transaction.
        now = datetime.datetime.utcnow()
        stmt = (
            pg_insert(User.__table__)
            .values(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                language_code=language_code,
                referral_code=_generate_referral_code(),
                last_active=now,
            )
            .on_conflict_do_nothing(index_elements=[User.telegram_id])
        )
        try:
            await self.session.execute(stmt)
            await self.session.commit()
        except IntegrityError:
            # Extremely rare: e.g. conflict on referral_code. Roll back and
            # fall through to re-fetch logic below.
            await self.session.rollback()

        # Re-fetch the user (either freshly inserted or created by a parallel
        # request that won the race).
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            # As a last resort, retry the insert a few times. This covers
            # the rare case of a referral_code collision when the row truly
            # did not exist, AND a concurrent insert that finished between
            # our SELECT and INSERT (race).
            for _ in range(3):
                try:
                    stmt = (
                        pg_insert(User.__table__)
                        .values(
                            telegram_id=telegram_id,
                            username=username,
                            first_name=first_name,
                            language_code=language_code,
                            referral_code=_generate_referral_code(),
                            last_active=now,
                        )
                        .on_conflict_do_nothing(index_elements=[User.telegram_id])
                    )
                    await self.session.execute(stmt)
                    await self.session.commit()
                except IntegrityError:
                    await self.session.rollback()
                    continue

                result = await self.session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()
                if user is not None:
                    break
            if user is None:
                raise RuntimeError(
                    f"Failed to get_or_create user telegram_id={telegram_id}"
                )

        # Refresh activity/profile fields if another request created the row.
        user.username = username
        user.first_name = first_name
        user.last_active = datetime.datetime.utcnow()
        user.deleted_at = None
        await self.session.commit()
        return user

    async def get_by_telegram_id(
        self, telegram_id: int, *, include_deleted: bool = False
    ) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def soft_delete(self, telegram_id: int) -> bool:
        """Mark a user as deleted, preserving rows for financial history."""
        result = await self.session.execute(
            update(User)
            .where(User.telegram_id == telegram_id, User.deleted_at.is_(None))
            .values(deleted_at=datetime.datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount > 0

    async def get_by_referral_code(self, code: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def update_balance(
        self,
        telegram_id: int,
        amount: int,
        *,
        commit: bool = True,
        allow_negative: bool = True,
    ) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        if not allow_negative and user.balance + amount < 0:
            return None
        user.balance += amount
        if commit:
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
            select(User)
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
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
            select(User.telegram_id).where(
                User.is_banned.is_(False), User.deleted_at.is_(None)
            )
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

    async def get_segmented_users(self, segment: str) -> Sequence[int]:
        if segment == "new_users":
            since = datetime.datetime.utcnow() - datetime.timedelta(days=7)
            result = await self.session.execute(
                select(User.telegram_id).where(User.created_at >= since, User.is_banned.is_(False))
            )
            return result.scalars().all()
        if segment == "trial_unused":
            result = await self.session.execute(
                select(User.telegram_id).where(User.trial_used.is_(False), User.is_banned.is_(False))
            )
            return result.scalars().all()
        if segment == "inactive":
            since = datetime.datetime.utcnow() - datetime.timedelta(days=14)
            result = await self.session.execute(
                select(User.telegram_id).where(
                    (User.last_active.is_(None) | (User.last_active < since)),
                    User.is_banned.is_(False),
                )
            )
            return result.scalars().all()
        if segment.startswith("lang:"):
            lang = segment.split(":", 1)[1]
            result = await self.session.execute(
                select(User.telegram_id).where(User.language_code == lang, User.is_banned.is_(False))
            )
            return result.scalars().all()
        return list(await self.get_all_telegram_ids())

    async def get_users_with_auto_renew(self) -> Sequence[User]:
        result = await self.session.execute(
            select(User).where(
                User.auto_renew.is_(True),
                User.is_banned.is_(False),
                User.deleted_at.is_(None),
            )
        )
        return result.scalars().all()
