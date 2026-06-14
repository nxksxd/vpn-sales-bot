"""Admin panel inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f465 Пользователи", callback_data="adm:users")],
            [InlineKeyboardButton(text="\U0001f4ca Статистика", callback_data="adm:stats")],
            [InlineKeyboardButton(text="\U0001f4e2 Рассылка", callback_data="adm:broadcast")],
            [InlineKeyboardButton(text="\u2699\ufe0f Настройки", callback_data="adm:settings")],
            [InlineKeyboardButton(text="\U0001f5a5 Статус сервера", callback_data="adm:server")],
            [InlineKeyboardButton(text="\u00ab Главное меню", callback_data="u:menu")],
        ]
    )


def admin_users_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f50d Поиск", callback_data="adm:user_search")],
            [InlineKeyboardButton(text="\U0001f4cb Список всех", callback_data="adm:user_list:0")],
            [InlineKeyboardButton(text="\u00ab Админ-панель", callback_data="adm:main")],
        ]
    )


def admin_user_card_kb(telegram_id: int) -> InlineKeyboardMarkup:
    tid = str(telegram_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u270f\ufe0f Изменить баланс",
                    callback_data=f"adm:bal:{tid}",
                ),
                InlineKeyboardButton(
                    text="\U0001f511 Ключи",
                    callback_data=f"adm:keys:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4c5 Подписка",
                    callback_data=f"adm:sub:{tid}",
                ),
                InlineKeyboardButton(
                    text="\U0001f6ab Бан/Разбан",
                    callback_data=f"adm:ban:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4e8 Сообщение",
                    callback_data=f"adm:msg:{tid}",
                ),
            ],
            [InlineKeyboardButton(text="\u00ab Пользователи", callback_data="adm:users")],
        ]
    )


def admin_key_actions_kb(telegram_id: int) -> InlineKeyboardMarkup:
    tid = str(telegram_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f504 Пересоздать ключ",
                    callback_data=f"adm:regen:{tid}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="\u23f8 Деактивировать",
                    callback_data=f"adm:deact:{tid}",
                ),
                InlineKeyboardButton(
                    text="\u25b6\ufe0f Активировать",
                    callback_data=f"adm:react:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f504 Сбросить трафик",
                    callback_data=f"adm:rst_traffic:{tid}",
                )
            ],
            [InlineKeyboardButton(text="\u00ab Карточка", callback_data=f"adm:card:{tid}")],
        ]
    )


def admin_sub_actions_kb(telegram_id: int) -> InlineKeyboardMarkup:
    tid = str(telegram_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="+7 дней", callback_data=f"adm:ext:7:{tid}"
                ),
                InlineKeyboardButton(
                    text="+30 дней", callback_data=f"adm:ext:30:{tid}"
                ),
                InlineKeyboardButton(
                    text="+90 дней", callback_data=f"adm:ext:90:{tid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u274c Отменить подписку",
                    callback_data=f"adm:cancel_sub:{tid}",
                )
            ],
            [InlineKeyboardButton(text="\u00ab Карточка", callback_data=f"adm:card:{tid}")],
        ]
    )


def admin_broadcast_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4e3 Всем пользователям", callback_data="adm:bc_all")],
            [
                InlineKeyboardButton(
                    text="\u2705 Активным подписчикам",
                    callback_data="adm:bc_active",
                )
            ],
            [
                InlineKeyboardButton(
                    text="\u26a0\ufe0f Истекает через 3 дня",
                    callback_data="adm:bc_expiring",
                )
            ],
            [InlineKeyboardButton(text="\u00ab Админ-панель", callback_data="adm:main")],
        ]
    )


def user_list_nav_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="\u25c0\ufe0f", callback_data=f"adm:user_list:{page - 1}")
        )
    nav.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(text="\u25b6\ufe0f", callback_data=f"adm:user_list:{page + 1}")
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav,
            [InlineKeyboardButton(text="\u00ab Пользователи", callback_data="adm:users")],
        ]
    )
