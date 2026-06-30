"""User settings handlers (auto-renewal toggle)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.session import async_session_factory
from bot.keyboards.user_kb import user_settings_kb
from bot.services.user_settings import UserSettingsService

router = Router(name="user_settings")


@router.callback_query(F.data == "u:settings")
async def cb_user_settings(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        settings_service = UserSettingsService(session)
        auto_renew = await settings_service.get_auto_renew(call.from_user.id)
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
        settings_service = UserSettingsService(session)
        new_value = await settings_service.toggle_auto_renew(call.from_user.id)
        if new_value is None:
            return

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
