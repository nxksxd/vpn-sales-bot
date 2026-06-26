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
from loguru import logger

import datetime
import json

from bot.config import settings
from bot.database.models import Subscription
from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.vpn_key import VpnKeyRepository
from bot.keyboards.user_kb import back_to_menu_kb, subscription_kb
from bot.services.qr_generator import generate_qr_buffer
from bot.services.subscription import SubscriptionService, UserFacingError
from bot.services.xui_client import XUIClient, XuiError
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
                reply_markup=subscription_kb(has_active=True, is_legacy=True),
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

    kb = subscription_kb(has_active=True, is_legacy=not is_subscription)
    if call.message:
        try:
            await call.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            await call.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=kb,
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


@router.callback_query(F.data == "sub:upgrade_key")
async def cb_upgrade_key(call: CallbackQuery) -> None:
    """Migrate a legacy subscription (no ``sub_id``) to the modern format.

    The handler is idempotent on the UI level: if the active subscription
    already has a ``sub_id``, we just show the existing subscription URL
    without bothering 3x-ui.
    """
    await call.answer("Обновляю ключ…")
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

        xui = XUIClient()
        try:
            service = SubscriptionService(session, xui)
            sub_url = await service.upgrade_to_subscription_link(active)
        except UserFacingError as e:
            if call.message:
                await call.message.edit_text(
                    e.user_message,
                    parse_mode="HTML",
                    reply_markup=subscription_kb(has_active=True, is_legacy=True),
                )
            return
        except Exception as e:
            logger.error("upgrade_to_subscription_link failed: {}", e)
            if call.message:
                await call.message.edit_text(
                    "❌ Не удалось обновить ключ. Попробуйте позже или "
                    "обратитесь в поддержку.",
                    parse_mode="HTML",
                    reply_markup=subscription_kb(has_active=True, is_legacy=True),
                )
            return
        finally:
            await xui.close()

    text = (
        "✅ <b>Ключ обновлён!</b>\n\n"
        "Теперь у вас современная ссылка-подписка. Скопируйте её и "
        "добавьте в приложение (V2RayTun, Hiddify, v2rayNG, Streisand и т.п.) "
        "как <b>«Subscription»</b> / <b>«Подписка»</b>:\n\n"
        f"{code(sub_url)}\n\n"
        "📱 <i>Тапните по ссылке — она скопируется. "
        "Конфиг будет обновляться автоматически.</i>"
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


# ── Key verification (no regeneration) ───────────────────────────────


def _fmt_bytes(value: int) -> str:
    """Pretty-print byte counts as KB / MB / GB."""
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        return "0 B"
    if value <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


async def _verify_client_on_panel(
    xui: XUIClient, sub: Subscription
) -> tuple[bool, str]:
    """Check that the user's client really exists on 3x-ui and is healthy.

    Returns ``(ok, human_readable_status_block)``.

    The method never modifies anything on the panel — it only reads inbound
    state and (optionally) per-client stats. This is what the
    «🔄 Обновить ключ VLESS» button is wired to: the user gets a clear
    confirmation that the existing key is still valid, without us issuing
    a new UUID / breaking their imported configuration.
    """
    if not sub.xui_client_id or not sub.xui_inbound_id:
        return False, "❌ Ключ не привязан к VPN-серверу."

    try:
        inbound_raw = await xui.get_inbound(sub.xui_inbound_id)
    except XuiError as e:
        logger.warning("verify_client: get_inbound failed: {}", e)
        return False, "⚠️ Не удалось связаться с VPN-сервером. Попробуйте позже."

    if not inbound_raw:
        return False, "❌ Не найден входящий профиль на сервере."

    # 3x-ui returns settings/streamSettings as JSON strings.
    settings_raw = inbound_raw.get("settings")
    if isinstance(settings_raw, str):
        try:
            settings_obj = json.loads(settings_raw)
        except (ValueError, TypeError):
            settings_obj = {}
    elif isinstance(settings_raw, dict):
        settings_obj = settings_raw
    else:
        settings_obj = inbound_raw.get("settings_obj") or {}

    clients = settings_obj.get("clients") or []
    client = next(
        (c for c in clients if c.get("id") == sub.xui_client_id), None
    )
    if client is None:
        return (
            False,
            "❌ Ваш ключ не найден на сервере. Обратитесь в поддержку — "
            "возможно, потребуется перевыпуск.",
        )

    if not client.get("enable", True):
        return (
            False,
            "⛔ Ключ найден, но отключён на сервере. Обратитесь в поддержку.",
        )

    notes: list[str] = []

    # Expiry (3x-ui stores it in milliseconds; 0 = unlimited).
    expiry_ms = client.get("expiryTime") or 0
    try:
        expiry_ms = int(expiry_ms)
    except (TypeError, ValueError):
        expiry_ms = 0
    if expiry_ms > 0:
        expiry_dt = datetime.datetime.utcfromtimestamp(expiry_ms / 1000)
        if expiry_dt <= datetime.datetime.utcnow():
            return (
                False,
                f"⌛ Срок действия ключа истёк ({expiry_dt:%d.%m.%Y %H:%M} UTC). "
                "Продлите подписку.",
            )
        notes.append(f"📅 Действует до: <b>{expiry_dt:%d.%m.%Y %H:%M} UTC</b>")
    else:
        notes.append("📅 Срок действия: <b>без ограничений</b>")

    # Traffic stats (best-effort — endpoint may not be available on every build).
    total_gb_raw = client.get("totalGB") or 0
    try:
        total_bytes_limit = int(total_gb_raw)
    except (TypeError, ValueError):
        total_bytes_limit = 0

    stats = None
    email = client.get("email") or ""
    if email:
        try:
            stats = await xui.get_client_stats(email)
        except Exception as e:  # pragma: no cover — best-effort
            logger.debug("verify_client: get_client_stats failed: {}", e)
            stats = None

    used_bytes = 0
    if isinstance(stats, dict):
        try:
            used_bytes = int(stats.get("up", 0)) + int(stats.get("down", 0))
        except (TypeError, ValueError):
            used_bytes = 0

    if total_bytes_limit > 0:
        if used_bytes >= total_bytes_limit:
            return (
                False,
                "📛 Превышен лимит трафика по ключу. Обратитесь в поддержку "
                "или продлите подписку.",
            )
        notes.append(
            f"📊 Трафик: <b>{_fmt_bytes(used_bytes)} / {_fmt_bytes(total_bytes_limit)}</b>"
        )
    else:
        notes.append(
            f"📊 Трафик: <b>{_fmt_bytes(used_bytes)} (без лимита)</b>"
        )

    return True, "\n".join(notes)


@router.callback_query(F.data == "sub:check_key")
async def cb_check_key(call: CallbackQuery) -> None:
    """Verify the existing key without issuing a new one.

    Reads the current client config from 3x-ui and tells the user whether
    their key is still valid (exists on the panel, enabled, not expired,
    within traffic limit). Никаких новых UUID не генерируется — пользователь
    может продолжать пользоваться уже импортированной ссылкой.
    """
    await call.answer("Проверяю ключ…")
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

        # Make sure the DB-side record is still in shape.
        key_repo = VpnKeyRepository(session)
        db_key = (
            await key_repo.get_by_client_id(active.xui_client_id)
            if active.xui_client_id
            else None
        )

        xui = XUIClient()
        try:
            ok, status_block = await _verify_client_on_panel(xui, active)
        finally:
            await xui.close()

    target, is_subscription = _resolve_key_target(active)

    if ok:
        header = (
            "✅ <b>Ваш ключ корректен и работает</b>\n\n"
            "Перевыпуск не требуется — продолжайте пользоваться уже "
            "добавленной в приложение ссылкой."
        )
        body_parts = [header, "", status_block]
        if db_key is not None and not db_key.is_active:
            body_parts.append(
                "\nℹ️ <i>В нашей базе ключ был помечен неактивным — "
                "обратитесь в поддержку, если возникают проблемы с подключением.</i>"
            )
        if target:
            body_parts.append("")
            if is_subscription:
                body_parts.append("🔗 <b>Ваша ссылка-подписка:</b>")
            else:
                body_parts.append("🔑 <b>Ваш ключ VLESS:</b>")
            body_parts.append(code(target))
        text = "\n".join(body_parts)
    else:
        text = (
            "⚠️ <b>Проблема с ключом</b>\n\n"
            f"{status_block}\n\n"
            "Если ошибка повторится — напишите в поддержку."
        )

    kb = subscription_kb(has_active=True, is_legacy=not is_subscription)
    if call.message:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
