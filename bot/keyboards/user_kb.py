"""User-facing inline keyboards and persistent reply keyboard."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.config import settings


# ── Persistent reply keyboard (always visible at bottom) ───────────

MENU_BTN_PROFILE = "\U0001f48e Мой профиль"
MENU_BTN_SUBS = "\U0001f511 Мои подписки"
MENU_BTN_BUY = "\U0001f6d2 Купить подписку"
MENU_BTN_TOPUP = "\U0001f4b0 Пополнить баланс"
MENU_BTN_KEY = "\U0001f510 Мой ключ"
MENU_BTN_SUPPORT = "\U0001f198 Поддержка"
MENU_BTN_GUIDE = "\U0001f4d6 Инструкция"
MENU_BTN_REF = "\U0001f465 Реферальная программа"
MENU_BTN_SETTINGS = "\u2699\ufe0f Настройки"

MENU_BUTTONS_MAP = {
    MENU_BTN_PROFILE: "u:profile",
    MENU_BTN_SUBS: "u:subs",
    MENU_BTN_BUY: "u:buy",
    MENU_BTN_TOPUP: "u:topup",
    MENU_BTN_KEY: "sub:show_key",
    MENU_BTN_SUPPORT: "u:support",
    MENU_BTN_GUIDE: "u:guide",
    MENU_BTN_REF: "u:ref",
    MENU_BTN_SETTINGS: "u:settings",
}


def persistent_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_BTN_PROFILE), KeyboardButton(text=MENU_BTN_KEY)],
            [KeyboardButton(text=MENU_BTN_BUY), KeyboardButton(text=MENU_BTN_TOPUP)],
            [KeyboardButton(text=MENU_BTN_SUBS), KeyboardButton(text=MENU_BTN_GUIDE)],
            [KeyboardButton(text=MENU_BTN_REF), KeyboardButton(text=MENU_BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f48e Мой профиль", callback_data="u:profile")],
            [InlineKeyboardButton(text="\U0001f511 Мои подписки", callback_data="u:subs")],
            [InlineKeyboardButton(text="\U0001f6d2 Купить подписку", callback_data="u:buy")],
            [InlineKeyboardButton(text="\U0001f4b0 Пополнить баланс", callback_data="u:topup")],
            [InlineKeyboardButton(text="\U0001f4d6 Инструкция", callback_data="u:guide")],
            [InlineKeyboardButton(text="\U0001f465 Реферальная программа", callback_data="u:ref")],
            [InlineKeyboardButton(text="\U0001f198 Поддержка", callback_data="u:support")],
        ]
    )


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u00ab Главное меню", callback_data="u:menu")],
        ]
    )


def buy_plan_kb(
    region_code: str | None = None,
    promo_code: str | None = None,
    product_code: str = "vless",
) -> InlineKeyboardMarkup:
    """Third step — pick a duration (plan) for the chosen product+region."""
    plans = settings.plans
    rows = []
    for key in plans:
        plan = settings.price_with_promo(key, promo_code)
        discount_text = f" (-{plan['discount']}%)" if plan['discount'] > 0 else ""
        promo_text = " +promo" if plan.get("promo_code") else ""
        text = f"{plan['label']} — {plan['rub']} ₽ ({plan['stars']} ⭐){discount_text}{promo_text}"
        # callback format: buy:<product>:<plan>:<region>[:<promo>]
        callback_parts = ["buy", product_code, key, region_code or "default"]
        if promo_code:
            callback_parts.append(promo_code.upper())
        rows.append(
            [InlineKeyboardButton(text=text, callback_data=":".join(callback_parts))]
        )
    rows.append(
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="u:promo")]
    )
    # Back button leads to region selection for the same product.
    back_cb = f"prod:{product_code}"
    if promo_code:
        back_cb += f":{promo_code.upper()}"
    rows.append(
        [InlineKeyboardButton(text="« Назад к региону", callback_data=back_cb)]
    )
    rows.append(
        [InlineKeyboardButton(text="« Главное меню", callback_data="u:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_purchase_kb(
    plan_type: str,
    region_code: str | None = None,
    promo_code: str | None = None,
    product_code: str = "vless",
) -> InlineKeyboardMarkup:
    # callback format: confirm_buy:<product>:<plan>:<region>[:<promo>]
    callback_parts = ["confirm_buy", product_code, plan_type, region_code or "default"]
    if promo_code:
        callback_parts.append(promo_code.upper())
    callback_data = ":".join(callback_parts)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить покупку",
                    callback_data=callback_data,
                ),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="u:buy")],
        ]
    )


def topup_kb() -> InlineKeyboardMarkup:
    amounts = [50, 100, 250, 500]
    rows = []
    for amount in amounts:
        rub = settings.stars_to_rub(amount)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{amount} \u2b50 = {rub} \u20bd",
                    callback_data=f"topup:{amount}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="\u270f\ufe0f Ввести свою сумму",
                callback_data="topup:custom",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="\u00ab Назад", callback_data="u:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_kb(
    has_active: bool = False, is_legacy: bool = False
) -> InlineKeyboardMarkup:
    """Inline keyboard for the subscription / key view.

    Кнопка «🔄 Обновить ключ VLESS» теперь всегда доступна при активной
    подписке. По нажатию ключ НЕ перевыпускается — выполняется только
    проверка, что текущий ключ корректен и активен на сервере 3x-ui.

    Для устаревших подписок (``is_legacy=True``) дополнительно
    показывается кнопка миграции на новый формат ссылки-подписки.
    """
    rows = []
    if has_active:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔑 Показать ключ VLESS",
                    callback_data="sub:show_key",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 QR-код ключа",
                    callback_data="sub:qr",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить ключ VLESS",
                    callback_data="sub:check_key",
                )
            ]
        )
        if is_legacy:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🆕 Обновить ключ (новая ссылка-подписка)",
                        callback_data="sub:upgrade_key",
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Продлить подписку",
                    callback_data="sub:renew",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🎁 Trial", callback_data="sub:trial")]
    )
    rows.append(
        [InlineKeyboardButton(text="📜 История подписок", callback_data="sub:history")]
    )
    rows.append(
        [InlineKeyboardButton(text="« Главное меню", callback_data="u:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renew_plan_kb() -> InlineKeyboardMarkup:
    plans = settings.plans
    rows = []
    for key, plan in plans.items():
        discount_text = f" (-{plan['discount']}%)" if plan['discount'] > 0 else ""
        text = f"{plan['label']} — {plan['rub']} ₽ ({plan['stars']} ⭐){discount_text}"
        rows.append(
            [InlineKeyboardButton(text=text, callback_data=f"renew:{key}")]
        )
    rows.append(
        [InlineKeyboardButton(text="⚡ Продлить на текущий тариф", callback_data="sub:renew_quick")]
    )
    rows.append(
        [InlineKeyboardButton(text="« Назад", callback_data="u:subs")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_settings_kb(auto_renew: bool) -> InlineKeyboardMarkup:
    toggle_text = "\u2705 Автопродление: ВКЛ" if auto_renew else "\u274c Автопродление: ВЫКЛ"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data="u:toggle_autorenew")],
            [InlineKeyboardButton(text="\u00ab Назад", callback_data="u:menu")],
        ]
    )


def guide_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4f1 Android", callback_data="guide:android")],
            [InlineKeyboardButton(text="\U0001f34f iOS", callback_data="guide:ios")],
            [InlineKeyboardButton(text="\U0001f5a5 Windows", callback_data="guide:windows")],
            [InlineKeyboardButton(text="\U0001f34e macOS", callback_data="guide:macos")],
            [InlineKeyboardButton(text="\U0001f427 Linux", callback_data="guide:linux")],
            [InlineKeyboardButton(text="\u00ab Главное меню", callback_data="u:menu")],
        ]
    )
