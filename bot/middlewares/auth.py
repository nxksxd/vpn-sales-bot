"""Ban check middleware — blocks banned users from interacting."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.database.repositories.user import UserRepository
from bot.database.session import async_session_factory


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        async with async_session_factory() as session:
            repo = UserRepository(session)
            db_user = await repo.get_by_telegram_id(user.id)

        if db_user is not None and db_user.is_banned:
            if hasattr(event, "answer"):
                try:
                    if hasattr(event, "data"):
                        await event.answer(
                            "Ваш аккаунт заблокирован.",
                            show_alert=True,
                        )
                    else:
                        await event.answer(
                            "\U0001f6ab Ваш аккаунт заблокирован. "
                            "Обратитесь в поддержку."
                        )
                except Exception:
                    pass
            return None

        return await handler(event, data)
