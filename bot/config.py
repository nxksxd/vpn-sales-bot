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

    # Subscription plans (prices in rubles)
    plan_1m_rub: int = 200
    plan_3m_rub: int = 500
    plan_6m_rub: int = 900
    plan_12m_rub: int = 1600

    # Telegram Stars conversion rate (1 star = X rubles)
    stars_to_rub_rate: float = 2.0

    # Traffic limit per client (GB, 0 = unlimited)
    traffic_limit_gb: int = 0

    # Referral system (bonus in rubles)
    referral_bonus_rub: int = 20

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

    def rub_to_stars(self, rub: int) -> int:
        """Convert rubles to Telegram Stars (rounded up)."""
        if self.stars_to_rub_rate <= 0:
            return rub
        import math
        return math.ceil(rub / self.stars_to_rub_rate)

    def stars_to_rub(self, stars: int) -> int:
        """Convert Telegram Stars to rubles (rounded down)."""
        return int(stars * self.stars_to_rub_rate)

    @property
    def plans(self) -> dict:
        return {
            "1m": {"label": "1 месяц", "rub": self.plan_1m_rub, "stars": self.rub_to_stars(self.plan_1m_rub), "days": 30, "discount": 0},
            "3m": {"label": "3 месяца", "rub": self.plan_3m_rub, "stars": self.rub_to_stars(self.plan_3m_rub), "days": 90, "discount": self._discount("3m")},
            "6m": {"label": "6 месяцев", "rub": self.plan_6m_rub, "stars": self.rub_to_stars(self.plan_6m_rub), "days": 180, "discount": self._discount("6m")},
            "12m": {"label": "12 месяцев", "rub": self.plan_12m_rub, "stars": self.rub_to_stars(self.plan_12m_rub), "days": 365, "discount": self._discount("12m")},
        }

    def _discount(self, plan: str) -> int:
        base = self.plan_1m_rub
        if base <= 0:
            return 0
        mapping = {"3m": (self.plan_3m_rub, 3), "6m": (self.plan_6m_rub, 6), "12m": (self.plan_12m_rub, 12)}
        price, months = mapping[plan]
        full_price = base * months
        if full_price <= 0:
            return 0
        return round((1 - price / full_price) * 100)


settings = Settings()
