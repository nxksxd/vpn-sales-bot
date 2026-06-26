"""Referral program handler."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.config import settings
from bot.database.session import async_session_factory
from bot.keyboards.user_kb import back_to_menu_kb
from bot.services.referral import ReferralService
from bot.utils.formatters import code, fmt_rub

router = Router(name="referral")


@router.callback_query(F.data == "u:ref")
async def cb_referral(call: CallbackQuery) -> None:
    await call.answer()
    user = call.from_user
    if user is None:
        return

    async with async_session_factory() as session:
        ref_service = ReferralService(session)
        stats = await ref_service.get_referral_stats(user.id)

    bot_info = await call.bot.get_me()
    bot_username = bot_info.username or ""
    ref_link = f"https://t.me/{bot_username}?start=ref_{stats['referral_code']}"

    text = (
        "\U0001f465 <b>Реферальная программа</b>\n\n"
        f"\U0001f517 Ваша реферальная ссылка:\n{code(ref_link)}\n\n"
        f"\U0001f465 Приглашено: <b>{stats['count']}</b> пользователей\n"
        f"\U0001f4b0 Заработано: <b>{fmt_rub(stats['earned'])}</b>\n\n"
        f"\U0001f381 Бонус за каждого реферала: <b>{fmt_rub(settings.referral_bonus_rub)}</b>\n\n"
        "<i>Поделитесь ссылкой с друзьями и получайте бонусы!</i>"
    )

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=back_to_menu_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=back_to_menu_kb()
            )
