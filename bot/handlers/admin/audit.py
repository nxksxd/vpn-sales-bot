from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.session import async_session_factory
from bot.keyboards.admin_kb import admin_main_kb
from bot.middlewares.admin_check import admin_only
from bot.services.audit_log import AuditLogService
from bot.utils.formatters import code, fmt_date

router = Router(name="admin_audit")


@router.callback_query(F.data == "adm:audit")
@router.callback_query(F.data.startswith("adm:audit:"))
@admin_only
async def cb_audit_logs(call: CallbackQuery) -> None:
    await call.answer()
    page = 0
    if call.data and call.data.startswith("adm:audit:"):
        page = max(0, int(call.data.split(":")[-1]))

    limit = 20
    async with async_session_factory() as session:
        logs = await AuditLogService(session).get_recent_page(page=page, limit=limit)

    if not logs:
        text = "🧾 <b>Audit log</b>\n\nЗаписей пока нет."
    else:
        lines = [f"🧾 <b>Audit log</b> (page {page + 1})\n"]
        for log in logs:
            target = code(log.target_user_id) if log.target_user_id else "—"
            lines.append(
                f"• {fmt_date(log.created_at)} | {code(log.admin_telegram_id)} | {log.action} | target={target}"
            )
        text = "\n".join(lines)

    if call.message:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_main_kb())
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=admin_main_kb())
