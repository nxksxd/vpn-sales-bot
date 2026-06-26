from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings


# Catalog of products the bot can sell. For now only VLESS subscription
# is supported, but the architecture (product → region → plan) is built
# so adding new products (e.g. Outline, Shadowsocks, dedicated IP) is a
# matter of appending an entry here and wiring its own purchase path.
PRODUCTS: list[dict] = [
    {
        "code": "vless",
        "label": "🔑 Ключ VLESS",
        "description": "Защищённый VPN-ключ протокола VLESS",
    },
]


def product_select_kb() -> InlineKeyboardMarkup:
    """First step of the purchase funnel — choose what to buy."""
    rows = [
        [InlineKeyboardButton(text=p["label"], callback_data=f"prod:{p['code']}")]
        for p in PRODUCTS
    ]
    rows.append([InlineKeyboardButton(text="🎁 Промокод", callback_data="u:promo")])
    rows.append([InlineKeyboardButton(text="« Главное меню", callback_data="u:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def region_select_kb(
    regions: list[dict] | None = None,
    product_code: str = "vless",
    promo_code: str | None = None,
) -> InlineKeyboardMarkup:
    """Second step — pick a server region for the chosen product."""
    rows = []
    source = regions or [
        {"code": code, "label": region.get("label", code)}
        for code, region in settings.server_regions.items()
    ]
    for region in source:
        cb_parts = ["region", product_code, region["code"]]
        if promo_code:
            cb_parts.append(promo_code.upper())
        rows.append([
            InlineKeyboardButton(
                text=f"🌍 {region['label']}",
                callback_data=":".join(cb_parts),
            )
        ])
    rows.append([InlineKeyboardButton(text="🎁 Промокод", callback_data="u:promo")])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="u:buy")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
