"""User profile handler."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.session import async_session_factory
from bot.database.repositories.user import UserRepository
from bot.keyboards.user_kb import back_to_menu_kb
from bot.utils.formatters import code, esc, fmt_date, fmt_rub

router = Router(name="profile")


@router.callback_query(F.data == "u:profile")
async def cb_profile(call: CallbackQuery) -> None:
    await call.answer()
    user = call.from_user
    if user is None:
        return

    async with async_session_factory() as session:
        repo = UserRepository(session)
        db_user = await repo.get_by_telegram_id(user.id)

    if db_user is None:
        if call.message:
            await call.message.edit_text(
                "\u274c Профиль не найден. Отправьте /start",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )
        return

    referral_count = 0
    async with async_session_factory() as session:
        repo = UserRepository(session)
        referral_count = await repo.get_referral_count(user.id)

    auto_renew_status = "\u2705 ВКЛ" if db_user.auto_renew else "\u274c ВЫКЛ"
    text = (
        "\U0001f48e <b>Мой профиль</b>\n\n"
        f"\U0001f194 ID: {code(db_user.telegram_id)}\n"
        f"\U0001f464 Username: @{esc(db_user.username or '—')}\n"
        f"\U0001f4b0 Баланс: <b>{fmt_rub(db_user.balance)}</b>\n"
        f"\U0001f504 Автопродление: {auto_renew_status}\n"
        f"\U0001f4c5 Дата регистрации: {fmt_date(db_user.created_at)}\n"
        f"\U0001f465 Рефералов: {referral_count}\n\n"
        f"\U0001f517 Реферальная ссылка:\n"
        f"{code(f'https://t.me/{(call.bot.token or '').split(':')[0] if call.bot else ''}?start=ref_{db_user.referral_code}')}"
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
