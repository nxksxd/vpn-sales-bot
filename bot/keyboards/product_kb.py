from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings


def region_select_kb(regions: list[dict] | None = None) -> InlineKeyboardMarkup:
    rows = []
    source = regions or [
        {"code": code, "label": region.get("label", code)}
        for code, region in settings.server_regions.items()
    ]
    for region in source:
        rows.append([
            InlineKeyboardButton(text=f"🌍 {region['label']}", callback_data=f"region:{region['code']}")
        ])
    rows.append([InlineKeyboardButton(text="🎁 Промокод", callback_data="u:promo")])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="u:buy")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
