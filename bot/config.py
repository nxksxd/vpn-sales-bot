"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Telegram
    bot_token: str = ""
    admin_telegram_id: int = 0

    # Database
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'vpn_bot.db'}"

    # 3x-ui Panel
    xui_url: str = "http://127.0.0.1:2053"
    xui_username: str = "admin"
    xui_password: str = ""
    xui_inbound_id: int = 1

    # Subscription plans (Telegram Stars)
    plan_1m_stars: int = 100
    plan_3m_stars: int = 250
    plan_6m_stars: int = 450
    plan_12m_stars: int = 800

    # Traffic limit per client (GB, 0 = unlimited)
    traffic_limit_gb: int = 0

    # Referral system
    referral_bonus_stars: int = 10

    # Notification schedule (days before expiry)
    notify_before_days: str = "3,1"

    # Server address for VLESS links
    server_address: str = ""

    # Rate limiting
    rate_limit_per_minute: int = 30

    # Support
    support_username: str = ""

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8"}

    @property
    def notify_days_list(self) -> List[int]:
        return [int(d.strip()) for d in self.notify_before_days.split(",") if d.strip()]

    @property
    def plans(self) -> dict:
        return {
            "1m": {"label": "1 месяц", "stars": self.plan_1m_stars, "days": 30, "discount": 0},
            "3m": {"label": "3 месяца", "stars": self.plan_3m_stars, "days": 90, "discount": self._discount("3m")},
            "6m": {"label": "6 месяцев", "stars": self.plan_6m_stars, "days": 180, "discount": self._discount("6m")},
            "12m": {"label": "12 месяцев", "stars": self.plan_12m_stars, "days": 365, "discount": self._discount("12m")},
        }

    def _discount(self, plan: str) -> int:
        base = self.plan_1m_stars
        if base <= 0:
            return 0
        mapping = {"3m": (self.plan_3m_stars, 3), "6m": (self.plan_6m_stars, 6), "12m": (self.plan_12m_stars, 12)}
        price, months = mapping[plan]
        full_price = base * months
        if full_price <= 0:
            return 0
        return round((1 - price / full_price) * 100)


settings = Settings()
