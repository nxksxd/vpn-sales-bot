from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.session import async_session_factory
from bot.database.repositories.promo_code import PromoCodeRepository
from bot.database.repositories.server_region import ServerRegionRepository
from bot.keyboards.admin_kb import admin_main_kb
from bot.middlewares.admin_check import admin_only
from bot.utils.formatters import code

router = Router(name="admin_catalog")


@router.callback_query(F.data == "adm:catalog")
@admin_only
async def cb_catalog(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        promo_repo = PromoCodeRepository(session)
        region_repo = ServerRegionRepository(session)
        promos = await promo_repo.get_all_active()
        regions = await region_repo.get_active_regions()

    lines = ["🗂 <b>Каталог продукта</b>\n"]

    lines.append("\n🌍 <b>Локации:</b>")
    if regions:
        for region in regions:
            lines.append(
                f"• {code(region.code)} — {region.label} | inbound={region.inbound_id} | {region.server_address}"
            )
    else:
        lines.append("• Нет активных локаций")

    lines.append("\n🎁 <b>Промокоды:</b>")
    if promos:
        for promo in promos:
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
