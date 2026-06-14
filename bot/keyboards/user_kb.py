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

MENU_BUTTONS_MAP = {
    MENU_BTN_PROFILE: "u:profile",
    MENU_BTN_SUBS: "u:subs",
    MENU_BTN_BUY: "u:buy",
    MENU_BTN_TOPUP: "u:topup",
    MENU_BTN_KEY: "sub:show_key",
    MENU_BTN_SUPPORT: "u:support",
    MENU_BTN_GUIDE: "u:guide",
    MENU_BTN_REF: "u:ref",
}


def persistent_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_BTN_PROFILE), KeyboardButton(text=MENU_BTN_KEY)],
            [KeyboardButton(text=MENU_BTN_BUY), KeyboardButton(text=MENU_BTN_TOPUP)],
            [KeyboardButton(text=MENU_BTN_SUBS), KeyboardButton(text=MENU_BTN_GUIDE)],
            [KeyboardButton(text=MENU_BTN_REF), KeyboardButton(text=MENU_BTN_SUPPORT)],
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


def buy_plan_kb() -> InlineKeyboardMarkup:
    plans = settings.plans
    rows = []
    for key, plan in plans.items():
        discount_text = f" (-{plan['discount']}%)" if plan['discount'] > 0 else ""
        text = f"{plan['label']} — {plan['stars']} \u2b50{discount_text}"
        rows.append(
            [InlineKeyboardButton(text=text, callback_data=f"buy:{key}")]
        )
    rows.append(
        [InlineKeyboardButton(text="\u00ab Назад", callback_data="u:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_purchase_kb(plan_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u2705 Подтвердить покупку",
                    callback_data=f"confirm_buy:{plan_type}",
                ),
            ],
            [InlineKeyboardButton(text="\u274c Отмена", callback_data="u:buy")],
        ]
    )


def topup_kb() -> InlineKeyboardMarkup:
    amounts = [100, 250, 500, 1000]
    rows = []
    for amount in amounts:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{amount} \u2b50",
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


def subscription_kb(has_active: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_active:
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f511 Показать ключ VLESS",
                    callback_data="sub:show_key",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f4f1 QR-код ключа",
                    callback_data="sub:qr",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f504 Продлить подписку",
                    callback_data="sub:renew",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="\U0001f4dc История подписок", callback_data="sub:history")]
    )
    rows.append(
        [InlineKeyboardButton(text="\u00ab Главное меню", callback_data="u:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renew_plan_kb() -> InlineKeyboardMarkup:
    plans = settings.plans
    rows = []
    for key, plan in plans.items():
        discount_text = f" (-{plan['discount']}%)" if plan['discount'] > 0 else ""
        text = f"{plan['label']} — {plan['stars']} \u2b50{discount_text}"
        rows.append(
            [InlineKeyboardButton(text=text, callback_data=f"renew:{key}")]
        )
    rows.append(
        [InlineKeyboardButton(text="\u00ab Назад", callback_data="u:subs")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
