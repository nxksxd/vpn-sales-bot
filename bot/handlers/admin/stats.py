"""Admin statistics handler."""

from __future__ import annotations

import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.keyboards.admin_kb import admin_main_kb
from bot.middlewares.admin_check import admin_only
from bot.utils.formatters import fmt_rub

router = Router(name="admin_stats")


@router.callback_query(F.data == "adm:stats")
@admin_only
async def cb_stats(call: CallbackQuery) -> None:
    await call.answer()

    now = datetime.datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - datetime.timedelta(days=7)
    month_ago = now - datetime.timedelta(days=30)

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        total_users = await user_repo.count_all()
        active_users = await user_repo.count_active()
        banned_users = await user_repo.count_banned()

        sub_repo = SubscriptionRepository(session)
        active_subs = await sub_repo.count_active()

        tx_repo = TransactionRepository(session)
        income_today = await tx_repo.sum_income_period(today)
        income_week = await tx_repo.sum_income_period(week_ago)
        income_month = await tx_repo.sum_income_period(month_ago)

    text = (
        "\U0001f4ca <b>Статистика</b>\n\n"
        f"\U0001f465 <b>Пользователи:</b>\n"
        f"  Всего: <b>{total_users}</b>\n"
        f"  Активных (7 дней): {active_users}\n"
        f"  Заблокированных: {banned_users}\n\n"
        f"\U0001f511 <b>Подписки:</b>\n"
        f"  Активных: <b>{active_subs}</b>\n\n"
        f"\U0001f4b0 <b>Доход:</b>\n"
        f"  Сегодня: <b>{fmt_rub(income_today)}</b>\n"
        f"  За неделю: {fmt_rub(income_week)}\n"
        f"  За месяц: {fmt_rub(income_month)}\n"
    )

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=admin_main_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=admin_main_kb()
            )
