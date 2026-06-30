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
from bot.utils import metrics
from bot.utils.formatters import fmt_rub

router = Router(name="admin_stats")


def _format_counter(value: int | None) -> int:
    return int(value or 0)


def build_metrics_text(snapshot: dict[str, int]) -> str:
    """Render in-process operational counters for the admin stats screen."""
    return (
        "📈 <b>Операционные метрики:</b>\n"
        f"  Успешных платежей: {_format_counter(snapshot.get(metrics.PAYMENTS_SUCCEEDED))}\n"
        f"  Ошибок платежей: {_format_counter(snapshot.get(metrics.PAYMENTS_FAILED))}\n"
        f"  Ошибок 3x-ui: {_format_counter(snapshot.get(metrics.XUI_ERRORS))}\n"
    )


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
        trial_unused = len(await user_repo.get_segmented_users("trial_unused"))
        inactive_users = len(await user_repo.get_segmented_users("inactive"))

        sub_repo = SubscriptionRepository(session)
        active_subs = await sub_repo.count_active()
        expiring_soon = len(await sub_repo.get_expiring_soon(3))

        tx_repo = TransactionRepository(session)
        income_today = await tx_repo.sum_income_period(today)
        income_week = await tx_repo.sum_income_period(week_ago)
        income_month = await tx_repo.sum_income_period(month_ago)

    metric_snapshot = metrics.snapshot()

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"  Всего: <b>{total_users}</b>\n"
        f"  Активных (7 дней): {active_users}\n"
        f"  Неактивных: {inactive_users}\n"
        f"  Без trial: {trial_unused}\n"
        f"  Заблокированных: {banned_users}\n\n"
        f"🔑 <b>Подписки:</b>\n"
        f"  Активных: <b>{active_subs}</b>\n"
        f"  Истекают за 3 дня: {expiring_soon}\n\n"
        f"💰 <b>Доход:</b>\n"
        f"  Сегодня: <b>{fmt_rub(income_today)}</b>\n"
        f"  За неделю: {fmt_rub(income_week)}\n"
        f"  За месяц: {fmt_rub(income_month)}\n\n"
        f"{build_metrics_text(metric_snapshot)}"
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
