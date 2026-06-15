"""User settings handlers (auto-renewal toggle)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.session import async_session_factory
from bot.database.repositories.user import UserRepository
from bot.keyboards.user_kb import user_settings_kb

router = Router(name="user_settings")


@router.callback_query(F.data == "u:settings")
async def cb_user_settings(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        repo = UserRepository(session)
        db_user = await repo.get_by_telegram_id(call.from_user.id)

    auto_renew = db_user.auto_renew if db_user else True
    text = (
        "\u2699\ufe0f <b>Настройки</b>\n\n"
        "Управление вашим аккаунтом:"
    )
    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=user_settings_kb(auto_renew)
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=user_settings_kb(auto_renew)
            )


@router.callback_query(F.data == "u:toggle_autorenew")
async def cb_toggle_autorenew(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        repo = UserRepository(session)
        db_user = await repo.get_by_telegram_id(call.from_user.id)
        if db_user is None:
            return

        new_value = not db_user.auto_renew
        await repo.set_auto_renew(call.from_user.id, new_value)

    status = "\u2705 включено" if new_value else "\u274c выключено"
    text = (
        "\u2699\ufe0f <b>Настройки</b>\n\n"
        f"Автопродление {status}.\n\n"
        "Управление вашим аккаунтом:"
    )
    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=user_settings_kb(new_value)
            )
        except Exception:
            pass
