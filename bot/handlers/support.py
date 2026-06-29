"""Support and connection guide handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.config import settings
from bot.keyboards.user_kb import back_to_menu_kb, guide_kb

router = Router(name="support")


@router.callback_query(F.data == "u:support")
async def cb_support(call: CallbackQuery) -> None:
    await call.answer()
    support = settings.support_username
    support_text = f"@{support}" if support else "администратору бота"

    text = (
        "\U0001f198 <b>Поддержка</b>\n\n"
        "Если у вас возникли вопросы или проблемы:\n\n"
        f"\U0001f4ac Напишите {support_text}\n"
        "\U0001f4e7 Или опишите проблему здесь, и мы ответим вам.\n\n"
        "<i>Обычно отвечаем в течение 24 часов.</i>"
    )
    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=back_to_menu_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=back_to_menu_kb()
            )


@router.callback_query(F.data == "u:guide")
async def cb_guide_menu(call: CallbackQuery) -> None:
    await call.answer()
    text = (
        "\U0001f4d6 <b>Инструкция по подключению</b>\n\n"
        "Выберите вашу платформу:"
    )
    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=guide_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=guide_kb()
            )


GUIDE_TEXTS = {
    "android": (
        "\U0001f4f1 <b>Android</b>\n\n"
        "1. Установите <b>v2rayNG</b> из Google Play\n"
        "   или <b>Hiddify</b>\n\n"
        "2. В боте откройте «\U0001f511 Мои подписки» → «Показать ключ VLESS»\n"
        "3. Скопируйте ссылку\n"
        "4. В приложении нажмите «+» → «Импорт из буфера»\n"
        "5. Нажмите кнопку подключения \u25b6\ufe0f\n\n"
        "\U0001f4f1 Или отсканируйте QR-код из бота."
    ),
    "ios": (
        "\U0001f34f <b>iOS</b>\n\n"
        "1. Установите <b>Streisand</b> или <b>V2Box</b> из App Store\n\n"
        "2. В боте откройте «\U0001f511 Мои подписки» → «Показать ключ VLESS»\n"
        "3. Скопируйте ссылку\n"
        "4. В приложении нажмите «+» → «Добавить из буфера»\n"
        "5. Нажмите кнопку подключения\n\n"
        "\U0001f4f1 Или отсканируйте QR-код."
    ),
    "windows": (
        "\U0001f5a5 <b>Windows</b>\n\n"
        "1. Скачайте <b>Hiddify</b> или <b>v2rayN</b>\n"
        "   с GitHub\n\n"
        "2. В боте откройте «\U0001f511 Мои подписки» → «Показать ключ VLESS»\n"
        "3. Скопируйте ссылку\n"
        "4. В приложении: «Servers» → «Import from clipboard»\n"
        "5. Нажмите «Connect»\n"
    ),
    "macos": (
        "\U0001f34e <b>macOS</b>\n\n"
        "1. Установите <b>V2Box</b> из App Store\n"
        "   или <b>Hiddify</b>\n\n"
        "2. В боте откройте «\U0001f511 Мои подписки» → «Показать ключ VLESS»\n"
        "3. Скопируйте ссылку\n"
        "4. В приложении добавьте сервер из буфера\n"
        "5. Подключитесь\n"
    ),
    "linux": (
        "\U0001f427 <b>Linux</b>\n\n"
        "1. Установите <b>Hiddify</b> или <b>Nekoray</b>\n\n"
        "2. В боте откройте «\U0001f511 Мои подписки» → «Показать ключ VLESS»\n"
        "3. Скопируйте ссылку\n"
        "4. Импортируйте конфигурацию\n"
        "5. Подключитесь\n\n"
        "Для CLI: используйте <code>xray</code> с JSON-конфигом."
    ),
}


@router.callback_query(F.data.startswith("guide:"))
async def cb_guide_platform(call: CallbackQuery) -> None:
    await call.answer()
    platform = call.data.split(":", 1)[1] if call.data else ""
    text = GUIDE_TEXTS.get(platform, "Инструкция не найдена.")

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=guide_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=guide_kb()
            )
