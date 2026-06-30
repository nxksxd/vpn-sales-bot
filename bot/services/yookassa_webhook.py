"""YooKassa webhook server — receives payment notifications via aiohttp."""

from __future__ import annotations

import json

from aiohttp import web
from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from bot.config import settings
from bot.database.models import User
from bot.database.repositories.payment_event import PaymentEventRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.database.session import async_session_factory
from bot.domain_enums import PaymentStatus, TransactionType
from bot.utils.observability import log_event

# YooKassa trusted IP ranges (from documentation)
YOOKASSA_TRUSTED_IPS = {
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.156.11",
    "77.75.156.35",
    "77.75.154.128/25",
    "2a02:5180::/32",
}


def _ip_in_network(ip: str, network: str) -> bool:
    """Check if an IP address belongs to a CIDR network."""
    import ipaddress

    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(network, strict=False)
    except ValueError:
        return False


def _is_trusted_ip(ip: str) -> bool:
    """Verify request IP against YooKassa trusted ranges."""
    for network in YOOKASSA_TRUSTED_IPS:
        if _ip_in_network(ip, network):
            return True
    return False


def _request_client_ip(request: web.Request) -> str:
    if settings.yookassa_trust_x_forwarded_for:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.remote or ""


async def handle_webhook(request: web.Request) -> web.Response:
    """Process incoming YooKassa webhook notification."""
    # IP verification. X-Forwarded-For is intentionally ignored by default:
    # only enable it when a trusted reverse proxy is the sole public entrypoint.
    client_ip = _request_client_ip(request)

    if not _is_trusted_ip(client_ip):
        logger.warning("YooKassa webhook from untrusted IP: {}", client_ip)
        return web.Response(status=403)

    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception):
        logger.error("YooKassa webhook: invalid JSON body")
        return web.Response(status=400)

    event_type = body.get("event")
    payment_obj = body.get("object", {})
    payment_id = payment_obj.get("id")
    status = payment_obj.get("status")

    if not payment_id:
        logger.error("YooKassa webhook: missing payment ID")
        return web.Response(status=400)

    logger.info(
        "YooKassa webhook received: event={} payment_id={} status={}",
        event_type,
        payment_id,
        status,
    )

    if event_type == "payment.succeeded":
        await _handle_payment_succeeded(payment_id, payment_obj)
    elif event_type == "payment.canceled":
        await _handle_payment_canceled(payment_id, payment_obj)
    else:
        logger.info("YooKassa webhook: unhandled event type {}", event_type)

    return web.Response(status=200)


async def _handle_payment_succeeded(payment_id: str, payment_obj: dict) -> None:
    """Process successful payment — credit user balance."""
    metadata = payment_obj.get("metadata", {})
    telegram_id_str = metadata.get("telegram_id")
    amount_rub_str = metadata.get("amount_rub")

    if not telegram_id_str or not amount_rub_str:
        # Fallback: get amount from payment object
        amount_data = payment_obj.get("amount", {})
        amount_value = amount_data.get("value", "0")
        amount_rub = int(float(amount_value))
        logger.warning(
            "YooKassa webhook: metadata incomplete for payment_id={}, "
            "falling back to amount from payment object: {}",
            payment_id,
            amount_rub,
        )
    else:
        amount_rub = int(amount_rub_str)

    try:
        telegram_id = int(telegram_id_str) if telegram_id_str else 0
    except (ValueError, TypeError):
        telegram_id = 0

    if telegram_id == 0:
        logger.error(
            "YooKassa webhook: cannot determine user for payment_id={}",
            payment_id,
        )
        return

    # Check if already processed (idempotency)
    async with async_session_factory() as session:
        payment_events = PaymentEventRepository(session)
        existing = await payment_events.get_by_charge_id(payment_id)
        if existing and existing.status == PaymentStatus.PAID:
            logger.warning(
                "YooKassa webhook: duplicate succeeded for payment_id={}",
                payment_id,
            )
            return

    # Credit user balance atomically in a fresh session
    async with async_session_factory() as session:
        tx_repo = TransactionRepository(session)
        try:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user is None:
                logger.error(
                    "YooKassa webhook: user not found telegram_id={}",
                    telegram_id,
                )
                return

            await tx_repo.create(
                user_id=telegram_id,
                tx_type=TransactionType.TOPUP,
                amount_rub=amount_rub,
                amount_stars=0,
                description=f"Пополнение через ЮKassa: {amount_rub} ₽",
                charge_id=payment_id,
                idempotency_key=f"yookassa:{payment_id}",
                rate_snapshot="yookassa",
                commit=False,
            )
            user.balance += amount_rub
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning(
                "YooKassa webhook: duplicate transaction for payment_id={}",
                payment_id,
            )
            return

    # Update payment event status
    async with async_session_factory() as session:
        payment_events = PaymentEventRepository(session)
        existing = await payment_events.get_by_charge_id(payment_id)
        if existing:
            existing.status = PaymentStatus.PAID
            await session.commit()
        else:
            await payment_events.create(
                user_id=telegram_id,
                status=PaymentStatus.PAID,
                amount_stars=0,
                amount_rub=amount_rub,
                charge_id=payment_id,
                payload=f"yookassa:topup:{amount_rub}",
            )

    # Notify user via bot
    await _notify_user_payment_success(telegram_id, amount_rub)

    logger.info(
        "YooKassa payment processed: user={} amount_rub={} payment_id={}",
        telegram_id,
        amount_rub,
        payment_id,
    )
    log_event(
        "yookassa_payment_processed",
        user_id=telegram_id,
        amount_rub=amount_rub,
        payment_id=payment_id,
        status="paid",
    )


async def _handle_payment_canceled(payment_id: str, payment_obj: dict) -> None:
    """Process canceled payment — update status."""
    async with async_session_factory() as session:
        payment_events = PaymentEventRepository(session)
        existing = await payment_events.get_by_charge_id(payment_id)
        if existing:
            if existing.status == PaymentStatus.PAID:
                logger.warning(
                    "YooKassa webhook: trying to cancel already paid payment_id={}",
                    payment_id,
                )
                return
            existing.status = PaymentStatus.FAILED
            cancellation = payment_obj.get("cancellation_details", {})
            reason = cancellation.get("reason", "unknown")
            existing.error_message = f"canceled: {reason}"
            await session.commit()

    metadata = payment_obj.get("metadata", {})
    telegram_id_str = metadata.get("telegram_id")
    if telegram_id_str:
        try:
            telegram_id = int(telegram_id_str)
            await _notify_user_payment_canceled(telegram_id)
        except (ValueError, TypeError):
            pass

    logger.info("YooKassa payment canceled: payment_id={}", payment_id)


async def _notify_user_payment_success(telegram_id: int, amount_rub: int) -> None:
    """Send success notification to user."""
    from aiogram import Bot

    from bot.keyboards.user_kb import back_to_menu_kb

    try:
        bot = Bot(token=settings.bot_token)
        # Get updated balance
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)
            balance = user.balance if user else amount_rub

        await bot.send_message(
            chat_id=telegram_id,
            text=(
                f"✅ <b>Оплата прошла успешно!</b>\n\n"
                f"Зачислено: <b>{amount_rub} ₽</b>\n"
                f"Баланс: <b>{balance} ₽</b>"
            ),
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
        )
        await bot.session.close()
    except Exception as e:
        logger.error("Failed to notify user {} about payment: {}", telegram_id, e)


async def _notify_user_payment_canceled(telegram_id: int) -> None:
    """Send cancellation notification to user."""
    from aiogram import Bot

    from bot.keyboards.user_kb import back_to_menu_kb

    try:
        bot = Bot(token=settings.bot_token)
        await bot.send_message(
            chat_id=telegram_id,
            text="❌ <b>Оплата отменена или не завершена.</b>\n\nПопробуйте ещё раз.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
        )
        await bot.session.close()
    except Exception as e:
        logger.error("Failed to notify user {} about cancellation: {}", telegram_id, e)


async def start_webhook_server() -> web.AppRunner | None:
    """Start aiohttp server for YooKassa webhooks. Returns runner or None if disabled."""
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        logger.info("YooKassa not configured, webhook server disabled")
        return None

    app = web.Application()
    webhook_path = "/yookassa/webhook"
    if settings.yookassa_webhook_secret:
        webhook_path = f"{webhook_path}/{settings.yookassa_webhook_secret}"
    app.router.add_post(webhook_path, handle_webhook)
    # Health check endpoint
    app.router.add_get("/health", _health_check)

    runner = web.AppRunner(app)
    await runner.setup()

    port = settings.yookassa_webhook_port
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("YooKassa webhook server started on port {}", port)
    return runner


async def _health_check(request: web.Request) -> web.Response:
    return web.Response(text="ok")
