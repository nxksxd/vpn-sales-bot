from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.session import async_session_factory
from bot.keyboards.admin_kb import admin_main_kb
from bot.middlewares.admin_check import admin_only
from bot.services.admin_catalog import AdminCatalogService
from bot.utils.formatters import code

router = Router(name="admin_catalog")


@router.callback_query(F.data == "adm:catalog")
@admin_only
async def cb_catalog(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        catalog = await AdminCatalogService(session).get_catalog()

    lines = ["🗂 <b>Каталог продукта</b>\n"]

    lines.append("\n🌍 <b>Локации:</b>")
    if catalog.regions:
        for region in catalog.regions:
            lines.append(
                f"• {code(region.code)} — {region.label} | inbound={region.inbound_id} | {region.server_address}"
            )
    else:
        lines.append("• Нет активных локаций")

    lines.append("\n🎁 <b>Промокоды:</b>")
    if catalog.promos:
        for promo in catalog.promos:
            limit = promo.usage_limit if promo.usage_limit is not None else "∞"
            lines.append(
                f"• {code(promo.code)} — {promo.discount_percent}% | used={promo.used_count}/{limit}"
            )
    else:
        lines.append("• Нет активных промокодов")

    text = "\n".join(lines)
    if call.message:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_main_kb())
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=admin_main_kb())
