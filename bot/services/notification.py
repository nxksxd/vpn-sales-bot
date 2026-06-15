"""Notification templates and sending logic."""

from __future__ import annotations

from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Notification
from bot.database.repositories.user import UserRepository


TEMPLATES = {
    "subscription_activated": (
        "\U0001f389 <b>Подписка активирована!</b>\n\n"
        "\U0001f4c5 Действует до: <code>{expires_at}</code>\n"
        "\U0001f511 Ваш ключ VLESS готов\n"
        "\U0001f4ca Трафик: {traffic_limit}\n\n"
        "Нажмите кнопку ниже чтобы получить ключ \U0001f447"
    ),
    "renewal_reminder_3d": (
        "\u26a0\ufe0f <b>Ваша подписка истекает через 3 дня</b>\n\n"
        "\U0001f4c5 Дата окончания: <code>{expires_at}</code>\n"
        "\U0001f4b0 Баланс: {balance} \u20bd\n\n"
        "Продлите подписку чтобы не потерять доступ"
    ),
    "renewal_reminder_1d": (
        "\U0001f6a8 <b>Осталось меньше 24 часов!</b>\n\n"
        "Ваша подписка истекает завтра.\n"
        "{autorenew_info}\n\n"
        "\U0001f4b0 Баланс: {balance} \u20bd"
    ),
    "subscription_expired": (
        "\u274c <b>Ваша подписка истекла</b>\n\n"
        "Доступ приостановлен.\n"
        "Пополните баланс и продлите подписку."
    ),
    "balance_topped_up": (
        "\u2705 <b>Баланс пополнен!</b>\n\n"
        "\U0001f4b0 Зачислено: +{amount} \u20bd ({stars} \u2b50)\n"
        "\U0001f48e Текущий баланс: {balance} \u20bd"
    ),
    "purchase_success": (
        "\u2705 <b>Подписка оформлена!</b>\n\n"
        "\U0001f4c5 Действует до: <code>{expires_at}</code>\n"
        "\U0001f4b0 Списано: {price} \u20bd\n"
        "\U0001f48e Остаток: {balance} \u20bd\n\n"
        "Нажмите «\U0001f511 Мой ключ» чтобы получить VLESS ссылку."
    ),
    "referral_bonus": (
        "\U0001f381 <b>Реферальный бонус!</b>\n\n"
        "Новый пользователь зарегистрировался по вашей ссылке.\n"
        "\U0001f4b0 Начислено: +{bonus} \u20bd\n"
        "\U0001f48e Текущий баланс: {balance} \u20bd"
    ),
    "autorenew_success": (
        "\u2705 <b>Подписка автоматически продлена!</b>\n\n"
        "\U0001f4c5 Действует до: <code>{expires_at}</code>\n"
        "\U0001f4b0 Списано: {price} \u20bd\n"
        "\U0001f48e Остаток: {balance} \u20bd"
    ),
    "autorenew_insufficient": (
        "\u26a0\ufe0f <b>Не удалось продлить подписку</b>\n\n"
        "На балансе недостаточно средств для автопродления.\n"
        "\U0001f4b0 Баланс: {balance} \u20bd\n"
        "\U0001f4b3 Требуется: {price} \u20bd\n\n"
        "Пополните баланс чтобы продлить подписку."
    ),
}


class NotificationService:
    def __init__(self, bot: Bot, session: AsyncSession) -> None:
        self.bot = bot
        self.session = session
        self.user_repo = UserRepository(session)

    async def send(
        self,
        telegram_id: int,
        template_key: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        subscription_id: Optional[int] = None,
        **kwargs: str,
    ) -> bool:
        template = TEMPLATES.get(template_key)
        if template is None:
            logger.warning("Unknown notification template: {}", template_key)
            return False

        text = template.format(**kwargs)

        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.warning(
                "Failed to send notification to {}: {}", telegram_id, e
            )
            return False

        notif = Notification(
            user_id=telegram_id,
            type=template_key,
            subscription_id=subscription_id,
        )
        self.session.add(notif)
        await self.session.commit()
        return True

    async def send_custom(
        self,
        telegram_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> bool:
        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return True
        except Exception as e:
            logger.warning(
                "Failed to send message to {}: {}", telegram_id, e
            )
            return False

    async def broadcast(
        self,
        telegram_ids: list[int],
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> tuple[int, int]:
        sent = 0
        failed = 0
        for tg_id in telegram_ids:
            ok = await self.send_custom(tg_id, text, reply_markup)
            if ok:
                sent += 1
            else:
                failed += 1
        return sent, failed
