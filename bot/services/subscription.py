"""Subscription lifecycle management.

All user-visible errors raised from this module are instances of
:class:`UserFacingError`, whose ``user_message`` is a polished, ready-to-send
Russian text that handlers can forward verbatim — no string surgery needed.

Internal/technical failures still bubble up as plain ``Exception`` /
``ValueError`` so observability (Sentry, logs) sees the original payload.
"""

from __future__ import annotations

import datetime
import json
import secrets
import uuid as uuid_mod
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import Subscription
from bot.domain_enums import SubscriptionStatus, TransactionType
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.database.repositories.vpn_key import VpnKeyRepository
from bot.services.xui_client import XUIClient, XuiError, build_vless_link
from bot.utils import metrics
from bot.utils.formatters import fmt_rub


# ── User-facing error type ───────────────────────────────────────────


class UserFacingError(ValueError):
    """An error whose ``user_message`` is safe to show to end users as-is.

    Inherits from ``ValueError`` so existing ``except ValueError`` blocks in
    handlers continue to catch it without code changes.
    """

    def __init__(self, user_message: str, *, log_detail: str | None = None) -> None:
        super().__init__(log_detail or user_message)
        self.user_message = user_message


def _insufficient_balance_error(have: int, need: int) -> UserFacingError:
    short = max(0, need - have)
    return UserFacingError(
        "💸 <b>Недостаточно средств</b>\n\n"
        f"На балансе: <b>{fmt_rub(have)}</b>\n"
        f"Нужно: <b>{fmt_rub(need)}</b>\n"
        f"Не хватает: <b>{fmt_rub(short)}</b>\n\n"
        "Пополните баланс в разделе «💰 Пополнить баланс» и попробуйте снова.",
        log_detail=f"insufficient_balance have={have} need={need}",
    )


def _is_client_missing(exc: XuiError) -> bool:
    """True if 3X-UI reports the client/record is already gone.

    Disabling or removing a client that no longer exists in the panel is a
    no-op for our purposes (the end state — client cannot connect — is already
    satisfied), so callers should treat this as success, not failure.
    """
    msg = (exc.message or "").lower()
    return exc.code == 404 or "record not found" in msg or "not found" in msg


def _xui_error(action: str, exc: XuiError) -> UserFacingError:
    """Wrap a low-level 3x-ui failure into a friendly message."""
    metrics.inc(metrics.XUI_ERRORS)
    return UserFacingError(
        "⚠️ <b>Не удалось связаться с VPN-сервером</b>\n\n"
        "Сервис временно недоступен. Пожалуйста, попробуйте через пару минут, "
        "а если проблема не уйдёт — напишите в поддержку.",
        log_detail=f"xui {action} failed: {exc.message}",
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _generate_sub_id(telegram_id: int) -> str:
    """Opaque, hard-to-guess token used as 3x-ui ``subId``.

    Uses ``secrets`` (not the UUID4 used for the client itself) so the
    subscription URL is not derivable from the client UUID, even if the
    latter ever leaks. Keep it short (<=24 chars) so the resulting URL
    is comfortable to copy.
    """
    return f"u{telegram_id}{secrets.token_urlsafe(9)}"


def _parse_inbound(inbound: dict | None) -> dict:
    """Decode the JSON fields 3x-ui returns as strings."""
    data: dict = dict(inbound or {})
    if isinstance(data.get("settings"), str):
        try:
            data["settings_obj"] = json.loads(data["settings"])
        except (ValueError, TypeError):
            data["settings_obj"] = {}
    stream_raw = data.get("streamSettings") or data.get("stream_settings")
    if isinstance(stream_raw, str):
        try:
            data["stream_obj"] = json.loads(stream_raw)
        except (ValueError, TypeError):
            data["stream_obj"] = {}
    elif isinstance(stream_raw, dict):
        data["stream_obj"] = stream_raw
    return data


async def _cleanup_provisioned_client(
    xui: XUIClient,
    inbound_id: int,
    client_id: str,
    email: str,
    reason: str,
) -> None:
    """Best-effort rollback for a 3x-ui client created before DB/payment failure."""
    try:
        await xui.delete_client(inbound_id, client_id, email=email)
        logger.warning(
            "Rolled back provisioned 3X-UI client {} after {}",
            client_id,
            reason,
        )
    except XuiError as exc:
        if _is_client_missing(exc):
            return
        logger.error(
            "Failed to roll back provisioned 3X-UI client {} after {}: {}",
            client_id,
            reason,
            exc,
        )


# ── Service ──────────────────────────────────────────────────────────


class SubscriptionService:
    ALLOWED_TRANSITIONS = {
        SubscriptionStatus.PENDING: {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED, SubscriptionStatus.TRIAL},
        SubscriptionStatus.TRIAL: {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED},
        SubscriptionStatus.ACTIVE: {SubscriptionStatus.GRACE_PERIOD, SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED},
        SubscriptionStatus.GRACE_PERIOD: {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED},
        SubscriptionStatus.SUSPENDED: {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED},
        SubscriptionStatus.EXPIRED: {SubscriptionStatus.ACTIVE},
        SubscriptionStatus.CANCELLED: set(),
    }

    def __init__(self, session: AsyncSession, xui: XUIClient) -> None:
        self.session = session
        self.xui = xui
        self.user_repo = UserRepository(session)
        self.sub_repo = SubscriptionRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.key_repo = VpnKeyRepository(session)

    def _ensure_transition(self, current: str, target: SubscriptionStatus) -> None:
        current_status = SubscriptionStatus(current)
        allowed = self.ALLOWED_TRANSITIONS.get(current_status, set())
        if target not in allowed and current_status != target:
            raise ValueError(f"Invalid subscription status transition: {current_status} -> {target}")

    async def purchase(
        self,
        telegram_id: int,
        plan_type: str,
        idempotency_key: str | None = None,
        is_trial: bool = False,
        inbound_id: int | None = None,
        server_address: str | None = None,
        region_code: str | None = None,
        promo_code: str | None = None,
    ) -> Optional[Subscription]:
        # Resolve effective inbound: caller-supplied (region picker) wins
        # over the legacy single-inbound setting from .env. Same for the
        # public server address shown in the VLESS link.
        effective_inbound_id = inbound_id if inbound_id is not None else settings.xui_inbound_id
        effective_server = (
            server_address
            or settings.server_address
            or settings.xui_url.split("://")[-1].split(":")[0]
        )
        plan = settings.plans.get(plan_type)

        if plan is None:
            raise UserFacingError(
                "⚠️ Этот тариф больше не доступен. Выберите другой в меню «🛒 Купить подписку».",
                log_detail=f"unknown plan: {plan_type}",
            )

        # Trial overrides: free, with configurable duration and traffic limit.
        if is_trial:
            plan = {
                **plan,
                "rub": 0,
                "stars": 0,
                "days": settings.trial_days,
            }
            effective_traffic_gb = settings.trial_traffic_limit_gb
        else:
            effective_traffic_gb = settings.traffic_limit_gb

        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            raise UserFacingError(
                "❌ Профиль не найден. Отправьте /start и попробуйте снова.",
                log_detail="user not found",
            )
        if user.is_banned:
            raise UserFacingError(
                "🚫 Ваш аккаунт заблокирован. Свяжитесь с поддержкой.",
                log_detail="user banned",
            )
        if not is_trial and user.balance < plan["rub"]:
            raise _insufficient_balance_error(user.balance, plan["rub"])

        # Идемпотентность: блокируем повтор только если у пользователя
        # ДЕЙСТВИТЕЛЬНО есть активная подписка от предыдущего вызова.
        # Если подписку удалили (вручную из БД или через админ-панель),
        # старая транзакция не должна мешать пользователю купить заново.
        existing = await self.sub_repo.get_active_by_user(telegram_id)

        if idempotency_key and existing is not None:
            existing_tx = await self.tx_repo.get_by_idempotency_key(idempotency_key)
            if existing_tx is not None:
                raise UserFacingError(
                    "✅ Эта покупка уже была обработана ранее. Загляните в «🔑 Мои подписки».",
                    log_detail="duplicate idempotency_key",
                )

        if existing is not None:
            raise UserFacingError(
                "ℹ️ У вас уже есть активная подписка.\n"
                "Чтобы добавить дни — воспользуйтесь кнопкой «🔄 Продлить подписку».",
                log_detail="active subscription exists",
            )

        # Если активной подписки нет, но в БД осталась "висящая" транзакция
        # с этим idempotency_key (например, после ручного удаления подписки),
        # удалим её, чтобы повторная вставка не упала на UNIQUE-конфликте.
        if idempotency_key:
            await self.tx_repo.delete_by_idempotency_key(idempotency_key)

        client_uuid = str(uuid_mod.uuid4())
        email = f"user_{telegram_id}_{client_uuid[:8]}"
        sub_id = _generate_sub_id(telegram_id)
        traffic_bytes = effective_traffic_gb * (1024 ** 3) if effective_traffic_gb > 0 else 0
        expiry_ms = int(
            (
                datetime.datetime.utcnow()
                + datetime.timedelta(days=plan["days"])
            ).timestamp()
            * 1000
        )

        # Determine XTLS flow: actually use settings.xui_flow only when the
        # inbound runs REALITY (the standard combo VLESS+REALITY+Vision).
        # For TLS/WS/etc., flow must stay empty or 3x-ui will reject the
        # connection.
        inbound_data = _parse_inbound(await self.xui.get_inbound(effective_inbound_id))
        stream_security = (inbound_data.get("stream_obj") or {}).get("security", "")
        effective_flow = settings.xui_flow if stream_security == "reality" else ""

        client_data = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "flow": effective_flow,
            "limitIp": settings.device_limit,
            "totalGB": traffic_bytes,
            "expiryTime": expiry_ms,
            "tgId": telegram_id,
            "subId": sub_id,
        }

        try:
            await self.xui.add_client(effective_inbound_id, client_data)
        except XuiError as e:
            logger.error(
                "Failed to create 3X-UI client in inbound {}: {}",
                effective_inbound_id,
                e,
            )
            raise _xui_error("add_client", e)

        port = inbound_data.get("port", 443)
        vless_link = build_vless_link(
            uuid=client_uuid,
            server=effective_server,
            port=port,
            inbound=inbound_data,
            email=email,
            flow=effective_flow,
        )


        try:
            if plan["rub"] > 0:
                user_after_debit = await self.user_repo.update_balance(
                    telegram_id,
                    -plan["rub"],
                    allow_negative=False,
                )
                if user_after_debit is None:
                    # Race: someone spent the balance between our check and the
                    # debit. Show the same friendly message.
                    raise _insufficient_balance_error(user.balance, plan["rub"])

                try:
                    await self.tx_repo.create(
                        user_id=telegram_id,
                        tx_type=TransactionType.PURCHASE,
                        amount_rub=-plan["rub"],
                        amount_stars=plan["stars"],
                        description=(
                            f"Trial {plan['label']} ({plan_type})"
                            if is_trial
                            else f"Подписка {plan['label']} ({plan_type})"
                        ),
                        idempotency_key=idempotency_key,
                        rate_snapshot=str(settings.stars_to_rub_rate),
                    )
                except IntegrityError as e:
                    await self.user_repo.update_balance(telegram_id, plan["rub"])
                    raise UserFacingError(
                        "✅ Эта покупка уже была обработана ранее.",
                        log_detail="idempotency conflict",
                    ) from e
            elif idempotency_key:
                # Free purchase (e.g. trial): record a zero-amount transaction so
                # the idempotency key prevents repeated activations.
                try:
                    await self.tx_repo.create(
                        user_id=telegram_id,
                        tx_type=TransactionType.PURCHASE,
                        amount_rub=0,
                        amount_stars=0,
                        description=(
                            f"Trial {plan['label']} ({plan_type})"
                            if is_trial
                            else f"Подписка {plan['label']} ({plan_type})"
                        ),
                        idempotency_key=idempotency_key,
                        rate_snapshot=str(settings.stars_to_rub_rate),
                    )
                except IntegrityError as e:
                    raise UserFacingError(
                        "✅ Trial уже был активирован.",
                        log_detail="trial idempotency conflict",
                    ) from e

            sub = await self.sub_repo.create(
                user_id=telegram_id,
                plan_type=plan_type,
                price_rub=plan["rub"],
                days=plan["days"],
                xui_client_id=client_uuid,
                xui_inbound_id=effective_inbound_id,
                vless_link=vless_link,
                traffic_limit_gb=effective_traffic_gb,
                is_trial=is_trial,
                sub_id=sub_id,
                region_code=region_code,
                promo_code=promo_code,
            )

            await self.key_repo.create(
                subscription_id=sub.id,
                user_id=telegram_id,
                xui_client_id=client_uuid,
                xui_inbound_id=effective_inbound_id,
                email=email,
                vless_link=vless_link,
            )
        except Exception:
            await _cleanup_provisioned_client(
                self.xui,
                effective_inbound_id,
                client_uuid,
                email,
                "purchase failure",
            )
            raise


        logger.info(
            "Subscription purchased: user={} plan={} uuid={} sub_id={}",
            telegram_id,
            plan_type,
            client_uuid,
            sub_id,
        )
        return sub

    async def renew(
        self,
        telegram_id: int,
        plan_type: str,
        transaction_description: str | None = None,
        idempotency_key: str | None = None,
    ) -> Optional[Subscription]:
        plan = settings.plans.get(plan_type)
        if plan is None:
            raise UserFacingError(
                "⚠️ Этот тариф больше не доступен. Выберите другой в меню «🔄 Продлить подписку».",
                log_detail=f"unknown plan: {plan_type}",
            )

        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            raise UserFacingError(
                "❌ Профиль не найден. Отправьте /start и попробуйте снова.",
                log_detail="user not found",
            )
        if user.balance < plan["rub"]:
            raise _insufficient_balance_error(user.balance, plan["rub"])

        existing = await self.sub_repo.get_active_by_user(telegram_id)

        # Идемпотентность только при наличии активной подписки —
        # см. комментарий в purchase().
        if idempotency_key and existing is not None:
            existing_tx = await self.tx_repo.get_by_idempotency_key(idempotency_key)
            if existing_tx is not None:
                raise UserFacingError(
                    "✅ Это продление уже было обработано ранее.",
                    log_detail="duplicate idempotency_key",
                )

        if existing is None:
            return await self.purchase(
                telegram_id,
                plan_type,
                idempotency_key=idempotency_key,
            )

        self._ensure_transition(existing.status, SubscriptionStatus.ACTIVE)

        if existing.xui_client_id:
            try:
                new_expiry = existing.expires_at + datetime.timedelta(days=plan["days"])
                expiry_ms = int(new_expiry.timestamp() * 1000)
                key = await self.key_repo.get_by_client_id(existing.xui_client_id)
                email = key.email if key else f"user_{telegram_id}"
                await self.xui.update_client(
                    existing.xui_inbound_id or settings.xui_inbound_id,
                    existing.xui_client_id,
                    {
                        "id": existing.xui_client_id,
                        "email": email,
                        "enable": True,
                        "expiryTime": expiry_ms,
                    },
                )
            except XuiError as e:
                logger.error("Failed to update 3X-UI client expiry: {}", e)
                raise _xui_error("update_client", e)

        user_after_debit = await self.user_repo.update_balance(
            telegram_id,
            -plan["rub"],
            allow_negative=False,
        )
        if user_after_debit is None:
            raise _insufficient_balance_error(user.balance, plan["rub"])

        try:
            await self.tx_repo.create(
                user_id=telegram_id,
                tx_type=TransactionType.PURCHASE,
                amount_rub=-plan["rub"],
                amount_stars=plan["stars"],
                description=transaction_description or f"Продление {plan['label']} ({plan_type})",
                idempotency_key=idempotency_key,
                rate_snapshot=str(settings.stars_to_rub_rate),
            )
        except IntegrityError as e:
            await self.user_repo.update_balance(telegram_id, plan["rub"])
            raise UserFacingError(
                "✅ Это продление уже было обработано ранее.",
                log_detail="idempotency conflict",
            ) from e

        sub = await self.sub_repo.extend(existing.id, plan["days"])
        logger.info(
            "Subscription renewed: user={} plan={} sub_id={}",
            telegram_id,
            plan_type,
            existing.id,
        )
        return sub

    async def deactivate(self, sub: Subscription) -> None:
        self._ensure_transition(sub.status, SubscriptionStatus.EXPIRED)
        if sub.xui_client_id and sub.xui_inbound_id:
            try:
                key = await self.key_repo.get_by_client_id(sub.xui_client_id)
                email = key.email if key else None
                await self.xui.update_client(
                    sub.xui_inbound_id,
                    sub.xui_client_id,
                    {
                        "id": sub.xui_client_id,
                        "email": email or f"user_{sub.user_id}",
                        "enable": False,
                    },
                )
            except XuiError as e:
                if _is_client_missing(e):
                    logger.warning(
                        "3X-UI client {} already absent, treating deactivation "
                        "as done: {}",
                        sub.xui_client_id,
                        e,
                    )
                else:
                    logger.error(
                        "Failed to disable 3X-UI client {}: {}", sub.xui_client_id, e
                    )
                    raise _xui_error("update_client", e)

        await self.sub_repo.set_status(sub.id, SubscriptionStatus.EXPIRED)
        await self.key_repo.deactivate_by_subscription(sub.id)
        logger.info(
            "Subscription deactivated: user={} sub_id={}",
            sub.user_id,
            sub.id,
        )

    async def mark_grace_period(self, sub: Subscription) -> None:
        self._ensure_transition(sub.status, SubscriptionStatus.GRACE_PERIOD)
        await self.sub_repo.mark_grace_period(sub.id)

    async def suspend(self, sub: Subscription) -> None:
        self._ensure_transition(sub.status, SubscriptionStatus.SUSPENDED)
        if sub.xui_client_id and sub.xui_inbound_id:
            try:
                key = await self.key_repo.get_by_client_id(sub.xui_client_id)
                email = key.email if key else f"user_{sub.user_id}"
                await self.xui.update_client(
                    sub.xui_inbound_id,
                    sub.xui_client_id,
                    {
                        "id": sub.xui_client_id,
                        "email": email,
                        "enable": False,
                    },
                )
            except XuiError as e:
                if _is_client_missing(e):
                    logger.warning(
                        "3X-UI client {} already absent, treating suspend as "
                        "done: {}",
                        sub.xui_client_id,
                        e,
                    )
                else:
                    raise _xui_error("update_client", e)
        await self.sub_repo.mark_suspended(sub.id)

    async def reactivate_key(self, sub: Subscription) -> None:
        self._ensure_transition(sub.status, SubscriptionStatus.ACTIVE)
        if sub.xui_client_id and sub.xui_inbound_id:
            try:
                key = await self.key_repo.get_by_client_id(sub.xui_client_id)
                email = key.email if key else f"user_{sub.user_id}"
                await self.xui.update_client(
                    sub.xui_inbound_id,
                    sub.xui_client_id,
                    {
                        "id": sub.xui_client_id,
                        "email": email,
                        "enable": True,
                    },
                )
                if key:
                    await self.key_repo.set_active(key.id, True)
            except XuiError as e:
                logger.error(
                    "Failed to reactivate 3X-UI client {}: {}",
                    sub.xui_client_id,
                    e,
                )
                raise _xui_error("update_client", e)

    async def upgrade_to_subscription_link(self, sub: Subscription) -> str:
        """Assign a ``subId`` to a legacy subscription and return its public URL.

        For subscriptions created before the ``sub_id`` field was introduced
        we never told 3x-ui to bind a subscription token to the client, so
        the panel can't serve a ``/sub/<subId>`` URL for them. This method:

        1. Generates a fresh, opaque ``subId``.
        2. Pushes it to 3x-ui via ``update_client`` (keeping all other
           client attributes intact — expiry, traffic limit, etc.).
        3. Persists the value in our DB so :func:`settings.subscription_url`
           can render the user-facing link on subsequent requests.

        Idempotent: if the subscription already has a ``sub_id``, we simply
        return the existing subscription URL without touching 3x-ui.
        """
        if not sub.xui_client_id or not sub.xui_inbound_id:
            raise UserFacingError(
                "⚠️ К этой подписке не привязан VPN-ключ. Обратитесь в поддержку.",
                log_detail="no client_id on subscription",
            )

        if sub.sub_id:
            existing_url = settings.subscription_url(sub.sub_id)
            if existing_url:
                return existing_url

        # Fetch the current client payload from the inbound so we don't
        # accidentally drop fields (expiryTime, totalGB, limitIp, tgId, …).
        inbound_raw = await self.xui.get_inbound(sub.xui_inbound_id)
        inbound_data = _parse_inbound(inbound_raw)
        clients = (inbound_data.get("settings_obj") or {}).get("clients") or []
        current = next(
            (c for c in clients if c.get("id") == sub.xui_client_id), None
        )

        key = await self.key_repo.get_by_client_id(sub.xui_client_id)
        email = (current or {}).get("email") or (key.email if key else f"user_{sub.user_id}")

        new_sub_id = _generate_sub_id(sub.user_id)

        # Build a complete client payload — start from what 3x-ui already
        # has so behaviour stays identical, just attach ``subId``.
        payload = dict(current or {})
        payload.update(
            {
                "id": sub.xui_client_id,
                "email": email,
                "enable": True,
                "subId": new_sub_id,
            }
        )

        try:
            await self.xui.update_client(
                sub.xui_inbound_id, sub.xui_client_id, payload
            )
        except XuiError as e:
            logger.error(
                "Failed to attach subId to client {}: {}", sub.xui_client_id, e
            )
            raise _xui_error("update_client", e)

        await self.sub_repo.set_sub_id(sub.id, new_sub_id)
        sub.sub_id = new_sub_id

        url = settings.subscription_url(new_sub_id)
        if not url:
            # Should never happen — settings.subscription_url falls back to
            # XUI_URL — but degrade gracefully if base URL is misconfigured.
            raise UserFacingError(
                "⚠️ Ключ обновлён, но базовый URL подписки не настроен. "
                "Сообщите администратору.",
                log_detail="subscription_url returned None after upgrade",
            )

        logger.info(
            "Subscription upgraded to subId: user={} sub={} sub_id={}",
            sub.user_id,
            sub.id,
            new_sub_id,
        )
        return url

    async def regenerate_key(self, sub: Subscription) -> Optional[str]:
        if not sub.xui_client_id or not sub.xui_inbound_id:
            raise UserFacingError(
                "⚠️ К этой подписке не привязан VPN-ключ. Обратитесь в поддержку.",
                log_detail="no client_id on subscription",
            )

        try:
            result = await self.xui.regenerate_client(
                sub.xui_inbound_id, sub.xui_client_id
            )
        except XuiError as e:
            raise _xui_error("regenerate_client", e)

        new_uuid = result["new_uuid"]
        server = settings.server_address or settings.xui_url.split("://")[-1].split(":")[0]
        inbound_data = _parse_inbound(await self.xui.get_inbound(sub.xui_inbound_id))
        port = inbound_data.get("port", 443)
        email = result.get("email", f"user_{sub.user_id}")
        stream_security = (inbound_data.get("stream_obj") or {}).get("security", "")
        effective_flow = settings.xui_flow if stream_security == "reality" else ""
        new_link = build_vless_link(
            uuid=new_uuid,
            server=server,
            port=port,
            inbound=inbound_data,
            email=email,
            flow=effective_flow,
        )

        sub.xui_client_id = new_uuid
        sub.vless_link = new_link
        await self.session.commit()

        key = await self.key_repo.get_by_client_id(result["old_uuid"])
        if key:
            await self.key_repo.update_vless_link(key.id, new_link, new_uuid)

        return new_link
