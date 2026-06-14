"""VPN key display and QR handlers."""

from __future__ import annotations


from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.keyboards.user_kb import back_to_menu_kb, subscription_kb
from bot.services.qr_generator import generate_qr_buffer
from bot.utils.formatters import code

router = Router(name="keys")


@router.callback_query(F.data == "sub:show_key")
async def cb_show_key(call: CallbackQuery) -> None:
    await call.answer()
    user = call.from_user
    if user is None:
        return

    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        active = await sub_repo.get_active_by_user(user.id)

    if active is None or not active.vless_link:
        if call.message:
            await call.message.edit_text(
                "\u274c У вас нет активного ключа VPN.\n"
                "Купите подписку чтобы получить ключ.",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )
        return

    text = (
        "\U0001f511 <b>Ваш ключ VLESS</b>\n\n"
        "Скопируйте ссылку ниже и вставьте в VPN-клиент:\n\n"
        f"{code(active.vless_link)}\n\n"
        "\U0001f4f1 <i>Нажмите на ссылку чтобы скопировать</i>"
    )

    if call.message:
        try:
            await call.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=subscription_kb(has_active=True),
            )
        except Exception:
            await call.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=subscription_kb(has_active=True),
            )


@router.callback_query(F.data == "sub:qr")
async def cb_show_qr(call: CallbackQuery, bot: Bot) -> None:
    await call.answer()
    user = call.from_user
    if user is None:
        return

    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        active = await sub_repo.get_active_by_user(user.id)

    if active is None or not active.vless_link:
        if call.message:
            await call.message.edit_text(
                "\u274c У вас нет активного ключа VPN.",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )
        return

    qr_buf = generate_qr_buffer(active.vless_link)
    if qr_buf is None:
        if call.message:
            await call.message.answer(
                "\u274c Не удалось сгенерировать QR-код.",
                reply_markup=back_to_menu_kb(),
            )
        return

    photo = BufferedInputFile(qr_buf.read(), filename="vpn_key_qr.png")
    chat_id = call.message.chat.id if call.message else call.from_user.id
    await bot.send_photo(
        chat_id=chat_id,
        photo=photo,
        caption=(
            "\U0001f4f1 <b>QR-код вашего ключа VLESS</b>\n\n"
            "Отсканируйте QR-код в VPN-клиенте."
        ),
        parse_mode="HTML",
    )
