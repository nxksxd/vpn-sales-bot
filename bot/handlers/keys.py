"""VPN key display and QR handlers.

User-visible UX rule: we never expose the raw VLESS inline string anymore.
Instead we show the 3x-ui *subscription URL* (``/sub/<subId>``), which:

* is short and fits a single Telegram line — easy to copy;
* is what every modern V2Ray/Xray client expects in its
  "Add subscription" dialog;
* lets us rotate the underlying VLESS config server-side without forcing
  the user to re-import anything.

The raw VLESS link is kept only as a fallback for legacy subscriptions
created before ``sub_id`` was introduced — in that case we tell the user
to regenerate the key to get the new subscription format.
"""

from __future__ import annotations


from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.config import settings
from bot.database.models import Subscription
from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.keyboards.user_kb import back_to_menu_kb, subscription_kb
from bot.services.qr_generator import generate_qr_buffer
from bot.utils.formatters import code

router = Router(name="keys")


# ── Shared rendering helpers ─────────────────────────────────────────


def _resolve_key_target(sub: Subscription) -> tuple[str | None, bool]:
    """Return ``(url_for_user, is_subscription_link)``.

    * ``url_for_user`` — what we put into the bot message / QR code.
    * ``is_subscription_link`` — ``True`` when it's a ``/sub/<subId>`` link
      (preferred), ``False`` when we had to fall back to the legacy
      VLESS inline string.
    """
    sub_url = settings.subscription_url(sub.sub_id)
    if sub_url:
        return sub_url, True
    if sub.vless_link:
        return sub.vless_link, False
    return None, False


def _no_key_text() -> str:
    return (
        "🔑 <b>У вас пока нет активного ключа</b>\n\n"
        "Оформите подписку, и ключ появится в этом меню."
    )


def _legacy_hint() -> str:
    return (
        "\n\nℹ️ <i>Это ваш старый формат ключа. Чтобы получить удобную "
        "ссылку-подписку — нажмите «Обновить ключ» в меню подписки.</i>"
    )


# ── Handlers ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "sub:show_key")
async def cb_show_key(call: CallbackQuery) -> None:
    await call.answer()
    user = call.from_user
    if user is None:
        return

    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        active = await sub_repo.get_active_by_user(user.id)

    if active is None:
        if call.message:
            await call.message.edit_text(
                _no_key_text(),
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )
        return

    target, is_subscription = _resolve_key_target(active)
    if target is None:
        if call.message:
            await call.message.edit_text(
                "⚠️ Ключ ещё не сформирован. Попробуйте через минуту "
                "или нажмите «Обновить ключ».",
                parse_mode="HTML",
                reply_markup=subscription_kb(has_active=True),
            )
        return

    if is_subscription:
        text = (
            "🔗 <b>Ваша ссылка-подписка</b>\n\n"
            "Скопируйте её и добавьте в приложение (V2RayTun, Hiddify, "
            "v2rayNG, Streisand и т.п.) как <b>«Subscription»</b> / "
            "<b>«Подписка»</b>:\n\n"
            f"{code(target)}\n\n"
            "📱 <i>Тапните по ссылке — она скопируется. "
            "Конфиг будет обновляться автоматически.</i>"
        )
    else:
        text = (
            "🔑 <b>Ваш ключ VLESS</b>\n\n"
            "Скопируйте ссылку ниже и добавьте её в приложение "
            "как <b>конфиг VLESS</b>:\n\n"
            f"{code(target)}"
            + _legacy_hint()
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

    if active is None:
        if call.message:
            await call.message.edit_text(
                _no_key_text(),
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )
        return

    target, is_subscription = _resolve_key_target(active)
    if target is None:
        if call.message:
            await call.message.edit_text(
                "⚠️ Ключ ещё не сформирован.",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )
        return

    qr_buf = generate_qr_buffer(target)
    if qr_buf is None:
        if call.message:
            await call.message.answer(
                "❌ Не удалось сгенерировать QR-код. Попробуйте позже.",
                reply_markup=back_to_menu_kb(),
            )
        return

    photo = BufferedInputFile(qr_buf.read(), filename="vpn_subscription_qr.png")
    chat_id = call.message.chat.id if call.message else call.from_user.id
    if is_subscription:
        caption = (
            "📱 <b>QR-код вашей подписки</b>\n\n"
            "В приложении выберите <b>«Add subscription»</b> и отсканируйте код."
        )
    else:
        caption = (
            "📱 <b>QR-код ключа VLESS</b>\n\n"
            "Отсканируйте в приложении (Import / Scan QR)."
        )
    await bot.send_photo(
        chat_id=chat_id,
        photo=photo,
        caption=caption,
        parse_mode="HTML",
    )
