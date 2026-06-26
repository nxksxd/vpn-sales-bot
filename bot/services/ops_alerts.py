"""Operational alert helpers."""

from __future__ import annotations

from aiogram import Bot
from loguru import logger

from bot.config import settings


async def alert_admin(bot: Bot, title: str, details: str) -> None:
    admin_id = settings.admin_telegram_id
    if not admin_id:
        return
    text = f"⚠️ <b>{title}</b>\n\n{details}"
    try:
        await bot.send_message(admin_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to alert admin: {}", e)
