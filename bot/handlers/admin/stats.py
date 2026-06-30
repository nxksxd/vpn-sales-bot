"""Admin statistics handler."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.session import async_session_factory
from bot.keyboards.admin_kb import admin_main_kb
from bot.services.admin_stats import AdminStatsService
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

    async with async_session_factory() as session:
        stats = await AdminStatsService(session).get_snapshot()

    metric_snapshot = metrics.snapshot()

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"  Всего: <b>{stats.total_users}</b>\n"
        f"  Активных (7 дней): {stats.active_users}\n"
        f"  Неактивных: {stats.inactive_users}\n"
        f"  Без trial: {stats.trial_unused}\n"
        f"  Заблокированных: {stats.banned_users}\n\n"
        f"🔑 <b>Подписки:</b>\n"
        f"  Активных: <b>{stats.active_subs}</b>\n"
        f"  Истекают за 3 дня: {stats.expiring_soon}\n\n"
        f"💰 <b>Доход:</b>\n"
        f"  Сегодня: <b>{fmt_rub(stats.income_today)}</b>\n"
        f"  За неделю: {fmt_rub(stats.income_week)}\n"
        f"  За месяц: {fmt_rub(stats.income_month)}\n\n"
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
