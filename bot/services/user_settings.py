"""User settings use cases."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories.user import UserRepository


class UserSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.user_repo = UserRepository(session)

    async def get_auto_renew(self, telegram_id: int, default: bool = True) -> bool:
        """Return user's auto-renew setting, or default for missing users."""
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        return default if user is None else user.auto_renew

    async def toggle_auto_renew(self, telegram_id: int) -> bool | None:
        """Toggle auto-renew and return the new value, or None for missing users."""
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return None

        new_value = not user.auto_renew
        await self.user_repo.set_auto_renew(telegram_id, new_value)
        return new_value
