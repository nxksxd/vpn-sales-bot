"""Admin panel main menu."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.keyboards.admin_kb import admin_main_kb
from bot.middlewares.admin_check import admin_only

router = Router(name="admin_main")


@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message) -> None:
    await message.answer(
        "\U0001f510 <b>Админ-панель</b>\n\nВыберите раздел:",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
    )


@router.callback_query(F.data == "adm:main")
@admin_only
async def cb_admin_main(call: CallbackQuery) -> None:
    await call.answer()
    if call.message:
        try:
            await call.message.edit_text(
                "\U0001f510 <b>Админ-панель</b>\n\nВыберите раздел:",
                parse_mode="HTML",
                reply_markup=admin_main_kb(),
            )
        except Exception:
            await call.message.answer(
                "\U0001f510 <b>Админ-панель</b>\n\nВыберите раздел:",
                parse_mode="HTML",
                reply_markup=admin_main_kb(),
            )
