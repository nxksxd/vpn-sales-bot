"""Background scheduled tasks for subscription management."""

from __future__ import annotations

import datetime
from typing import Optional

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from bot.config import settings
from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.database.repositories.vpn_key import VpnKeyRepository
from bot.services.notification import NotificationService
from bot.services.ops_alerts import alert_admin
from bot.services.subscription import SubscriptionService
from bot.services.xui_client import XUIClient
from bot.utils.formatters import fmt_date, fmt_rub


scheduler = AsyncIOScheduler(timezone="UTC")
_bot: Optional[Bot] = None


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    global _bot
    _bot = bot

    scheduler.add_job(
        check_expiring_subscriptions,
        "interval",
        hours=1,
        id="check_expiring",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        deactivate_expired_subscriptions,
        "interval",
        minutes=15,
        id="deactivate_expired",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        sync_with_xui,
        "interval",
        hours=6,
        id="sync_xui",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        send_daily_report,
        "cron",
        hour=9,
        minute=0,
        id="daily_report",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        process_auto_renewals,
        "interval",
        hours=1,
        id="auto_renewals",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    return scheduler


async def check_expiring_subscriptions() -> None:
    if _bot is None:
        return

    logger.info("Checking expiring subscriptions...")

    for days in settings.notify_days_list:
        async with async_session_factory() as session:
            sub_repo = SubscriptionRepository(session)
            expiring = await sub_repo.get_expiring_soon(days)

            notif = NotificationService(_bot, session)
            user_repo = UserRepository(session)

            for sub in expiring:
                from bot.database.models import Notification
                from sqlalchemy import select

                already_sent = await session.execute(
                    select(Notification).where(
                        Notification.user_id == sub.user_id,
                        Notification.subscription_id == sub.id,
                        Notification.type == f"renewal_reminder_{days}d",
                    )
                )
                if already_sent.scalar_one_or_none() is not None:
                    continue

                user = await user_repo.get_by_telegram_id(sub.user_id)
                balance = user.balance if user else 0
                if days == 1 and sub.status == "active":
                    await sub_repo.mark_grace_period(sub.id)
                    sub.status = "grace_period"

                template_key = f"renewal_reminder_{days}d"
                if template_key not in ("renewal_reminder_3d", "renewal_reminder_1d"):
                    template_key = "renewal_reminder_3d" if days >= 3 else "renewal_reminder_1d"

                extra_kwargs: dict[str, str] = {
                    "expires_at": fmt_date(sub.expires_at),
                    "balance": str(balance),
                }
                if template_key == "renewal_reminder_1d":
                    if user and user.auto_renew:
                        extra_kwargs["autorenew_info"] = "Автопродление включено — подписка будет продлена автоматически."
                    else:
                        extra_kwargs["autorenew_info"] = "Продлите сейчас чтобы сохранить доступ."

                await notif.send(
                    sub.user_id,
                    template_key,
                    subscription_id=sub.id,
                    **extra_kwargs,
                )
                logger.info(
                    "Sent {}-day reminder to user {}", days, sub.user_id
                )


async def deactivate_expired_subscriptions() -> None:
    if _bot is None:
        return

    logger.info("Checking for expired subscriptions...")

    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        expired = await sub_repo.get_expired()

        if not expired:
            return

        xui = XUIClient()
        try:
            sub_service = SubscriptionService(session, xui)
            notif = NotificationService(_bot, session)

            for sub in expired:
                try:
                    await sub_service.deactivate(sub)
                    await notif.send(
                        sub.user_id,
                        "subscription_expired",
                        subscription_id=sub.id,
                    )
                    logger.info(
                        "Deactivated expired subscription: user={} sub_id={}",
                        sub.user_id,
                        sub.id,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to deactivate sub {}: {}", sub.id, e
                    )
        finally:
            await xui.close()


async def sync_with_xui() -> None:
    logger.info("Syncing with 3x-ui panel...")

    xui = XUIClient()
    try:
        ping = await xui.ping()
        if not ping:
            logger.warning("3x-ui panel is unreachable, skipping sync")
            if _bot is not None:
                await alert_admin(_bot, "3x-ui недоступен", "Синхронизация пропущена: панель 3x-ui не отвечает.")
            return

        async with async_session_factory() as session:
            sub_repo = SubscriptionRepository(session)
            active_subs = await sub_repo.get_all_active()
            key_repo = VpnKeyRepository(session)

            onlines = await xui.get_onlines()

            for sub in active_subs:
                if not sub.xui_client_id:
                    continue

                try:
                    key = await key_repo.get_by_client_id(sub.xui_client_id)
                    if key and key.email:
                        stats = await xui.get_client_stats(key.email)
                        if stats is not None:
                            logger.debug(
                                "Sync: user={} email={} stats={}",
                                sub.user_id,
                                key.email,
                                stats,
                            )
                except Exception as e:
                    logger.warning(
                        "Sync failed for client {}: {}",
                        sub.xui_client_id,
                        e,
                    )

        logger.info("3x-ui sync completed. Online clients: {}", len(onlines))
    except Exception as e:
        logger.error("3x-ui sync error: {}", e)
        if _bot is not None:
            await alert_admin(_bot, "Ошибка синхронизации 3x-ui", str(e)[:500])
    finally:
        await xui.close()


async def send_daily_report() -> None:
    if _bot is None:
        return

    admin_id = settings.admin_telegram_id
    if not admin_id:
        return

    logger.info("Sending daily report to admin...")

    now = datetime.datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - datetime.timedelta(days=1)

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        from bot.database.repositories.transaction import TransactionRepository

        tx_repo = TransactionRepository(session)

        total_users = await user_repo.count_all()
        active_subs = await sub_repo.count_active()
        income_today = await tx_repo.sum_income_period(today)
        income_yesterday = await tx_repo.sum_income_period(yesterday)
        new_txs_today = await tx_repo.count_since(today)

        expiring_3d = await sub_repo.get_expiring_soon(3)

    text = (
        "\U0001f4ca <b>Ежедневный отчёт</b>\n\n"
        f"\U0001f4c5 {now.strftime('%d.%m.%Y')}\n\n"
        f"\U0001f465 Пользователей: {total_users}\n"
        f"\U0001f511 Активных подписок: {active_subs}\n"
        f"\U0001f4b0 Доход сегодня: {fmt_rub(income_today)}\n"
        f"\U0001f4b0 Доход вчера: {fmt_rub(income_yesterday)}\n"
        f"\U0001f4b3 Транзакций сегодня: {new_txs_today}\n"
        f"\u26a0\ufe0f Истекает в ближайшие 3 дня: {len(expiring_3d)}\n"
    )

    try:
        await _bot.send_message(
            chat_id=admin_id, text=text, parse_mode="HTML"
        )
        logger.info("Daily report sent to admin {}", admin_id)
    except Exception as e:
        logger.error("Failed to send daily report: {}", e)


async def process_auto_renewals() -> None:
    """Process auto-renewals for subscriptions expiring within 1 day."""
    if _bot is None:
        return

    logger.info("Processing auto-renewals...")

    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        user_repo = UserRepository(session)
        tx_repo = TransactionRepository(session)
        notif = NotificationService(_bot, session)

        expiring = await sub_repo.get_expiring_soon(1)

        for sub in expiring:
            user = await user_repo.get_by_telegram_id(sub.user_id)
            if user is None or not user.auto_renew:
                continue

            plan = settings.plans.get(sub.plan_type)
            if plan is None:
                plan = settings.plans.get("1m")
            if plan is None:
                continue

            price_rub = plan["rub"]
            cycle_key = f"autorenew:{sub.id}:{sub.expires_at.isoformat()}"
            existing_attempt = await tx_repo.get_by_idempotency_key(cycle_key)
            if existing_attempt is not None:
                continue

            if user.balance >= price_rub:
                xui = XUIClient()
                try:
                    sub_service = SubscriptionService(session, xui)
                    renewed_sub = await sub_service.renew(
                        sub.user_id,
                        sub.plan_type,
                        transaction_description=f"Продление {plan['label']} ({sub.plan_type}) [{cycle_key}]",
                        idempotency_key=cycle_key,
                    )
                    if renewed_sub:
                        updated_user = await user_repo.get_by_telegram_id(sub.user_id)
                        new_balance = updated_user.balance if updated_user else 0
                        await notif.send(
                            sub.user_id,
                            "autorenew_success",
                            subscription_id=sub.id,
                            expires_at=fmt_date(renewed_sub.expires_at),
                            price=str(price_rub),
                            balance=str(new_balance),
                        )
                        logger.info(
                            "Auto-renewed subscription: user={} plan={}",
                            sub.user_id,
                            sub.plan_type,
                        )
                except Exception as e:
                    logger.error(
                        "Auto-renewal failed for user {}: {}",
                        sub.user_id,
                        e,
                    )
                    await alert_admin(
                        _bot,
                        "Ошибка автопродления",
                        f"user={sub.user_id} plan={sub.plan_type} error={str(e)[:300]}",
                    )
                finally:
                    await xui.close()
            else:
                already_notified = await notif.was_sent(
                    sub.user_id,
                    "autorenew_insufficient",
                    subscription_id=sub.id,
                    since=datetime.datetime.utcnow() - datetime.timedelta(hours=12),
                )
                if not already_notified:
                    await notif.send(
                        sub.user_id,
                        "autorenew_insufficient",
                        subscription_id=sub.id,
                        balance=str(user.balance),
                        price=str(price_rub),
                    )
                logger.info(
                    "Auto-renewal insufficient balance: user={} balance={} required={}",
                    sub.user_id,
                    user.balance,
                    price_rub,
                )
