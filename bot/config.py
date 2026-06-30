"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Telegram
    bot_token: str = ""
    admin_telegram_id: int = 0

    # Database
    database_url: str = "postgresql+asyncpg://vpn_bot:change_me@postgres:5432/vpn_bot"

    # FSM storage. Empty = in-memory (dev); set redis://... in production.
    redis_url: str = ""

    # 3x-ui Panel
    xui_url: str = "http://127.0.0.1:2053"
    xui_username: str = "admin"
    xui_password: str = ""
    xui_inbound_id: int = 1
    # XTLS flow для VLESS-клиентов (актуально для REALITY-инбаундов).
    # Стандарт для VLESS+REALITY — "xtls-rprx-vision". Поставьте пустую
    # строку, если ваш inbound его не использует (например, VLESS+TLS+WS).
    xui_flow: str = "xtls-rprx-vision"

    # Subscription URL (3x-ui sub link). If empty — derived from xui_url.
    # Example public form: https://panel.example.com:2096/sub/<subId>
    subscription_url_base: str = ""
    # Path prefix configured in 3x-ui "Subscription" settings (default: /sub/).
    subscription_path: str = "/sub/"

    # Subscription plans (prices in rubles)
    plan_1m_rub: int = 200
    plan_3m_rub: int = 500
    plan_6m_rub: int = 900
    plan_12m_rub: int = 1600

    # Telegram Stars conversion rate (1 star = X rubles)
    stars_to_rub_rate: float = 2.0

    # Traffic limit per client (GB, 0 = unlimited)
    traffic_limit_gb: int = 0

    # Device limit per client (max simultaneous IPs, 0 = unlimited)
    device_limit: int = 0

    # Referral system (base bonus in rubles; used when no tier matches)
    referral_bonus_rub: int = 20
    # Optional tiered bonuses by total referral count, e.g.
    # [{"min_referrals": 5, "bonus_rub": 30}, {"min_referrals": 20, "bonus_rub": 50}]
    referral_tiers_json: str = "[]"

    # Notification schedule (days before expiry)
    notify_before_days: str = "3,1"

    # Server address for VLESS links
    server_address: str = ""
    server_regions_json: str = '{"default": {"label": "Автовыбор", "server_address": "", "inbound_id": 1}}'

    # Product features
    promo_codes_json: str = '{}'
    trial_days: int = 1
    trial_traffic_limit_gb: int = 5

    # Rate limiting
    rate_limit_per_minute: int = 30

    # Support
    support_username: str = ""

    # Encryption key for sensitive DB fields (Fernet, urlsafe-base64).
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Empty = fields stored in plaintext (dev only; not for production).
    encryption_key: str = ""

    # YooKassa
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = "https://t.me/portalkey_bot"
    yookassa_webhook_port: int = 8080
    yookassa_webhook_secret: str = ""
    yookassa_trust_x_forwarded_for: bool = False

    # Observability
    sentry_dsn: str = ""  # empty = Sentry disabled

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        # Ignore variables in .env that are meant for other services
        # (e.g. POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB consumed by the
        # postgres container via docker-compose). Without this, pydantic v2
        # raises "Extra inputs are not permitted".
        "extra": "ignore",
    }

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

    def _referral_tiers(self) -> list[tuple[int, int]]:
        """Parsed (min_referrals, bonus_rub) tiers sorted ascending."""
        try:
            raw = json.loads(self.referral_tiers_json or "[]")
        except (ValueError, TypeError):
            return []
        tiers = [
            (int(t["min_referrals"]), int(t["bonus_rub"]))
            for t in raw
            if "min_referrals" in t and "bonus_rub" in t
        ]
        return sorted(tiers, key=lambda x: x[0])

    def referral_bonus_for(self, referral_count: int) -> int:
        """Bonus for the referral that brings the referrer to ``referral_count``.

        Falls back to the flat ``referral_bonus_rub`` when no tiers are set.
        """
        bonus = self.referral_bonus_rub
        for min_referrals, tier_bonus in self._referral_tiers():
            if referral_count >= min_referrals:
                bonus = tier_bonus
            else:
                break
        return bonus

    def referral_total_earned(self, referral_count: int) -> int:
        """Cumulative bonus earned across ``referral_count`` referrals."""
        return sum(self.referral_bonus_for(i) for i in range(1, referral_count + 1))

    @property
    def server_regions(self) -> dict:
        """Legacy JSON fallback for server regions.

        Prefer DB-backed ServerRegion records in runtime code.
        """
        try:
            return json.loads(self.server_regions_json or "{}")
        except ValueError:
            return {}

    @property
    def promo_codes(self) -> dict:
        """Legacy JSON fallback for promo codes.

        Prefer DB-backed PromoCode records in runtime code.
        """
        try:
            return json.loads(self.promo_codes_json or "{}")
        except ValueError:
            return {}

    @property
    def plans(self) -> dict:
        return {
            "1m": {"label": "1 месяц", "rub": self.plan_1m_rub, "stars": self.rub_to_stars(self.plan_1m_rub), "days": 30, "discount": 0},
            "3m": {"label": "3 месяца", "rub": self.plan_3m_rub, "stars": self.rub_to_stars(self.plan_3m_rub), "days": 90, "discount": self._discount("3m")},
            "6m": {"label": "6 месяцев", "rub": self.plan_6m_rub, "stars": self.rub_to_stars(self.plan_6m_rub), "days": 180, "discount": self._discount("6m")},
            "12m": {"label": "12 месяцев", "rub": self.plan_12m_rub, "stars": self.rub_to_stars(self.plan_12m_rub), "days": 365, "discount": self._discount("12m")},
        }

    def price_with_promo(self, plan_type: str, promo_code: str | None = None) -> dict:
        plan = dict(self.plans[plan_type])
        promo = self.promo_codes.get((promo_code or "").strip().upper())
        if not promo:
            return plan
        discount_percent = int(promo.get("discount_percent", 0))
        if discount_percent > 0:
            plan["rub"] = max(0, round(plan["rub"] * (100 - discount_percent) / 100))
            plan["stars"] = self.rub_to_stars(plan["rub"])
            plan["promo_code"] = (promo_code or "").strip().upper()
            plan["promo_discount_percent"] = discount_percent
        return plan

    def subscription_url(self, sub_id: str | None) -> str | None:
        """Build the public 3x-ui subscription URL for the given subId.

        Returns ``None`` when ``sub_id`` is empty so callers can fall back to
        the raw VLESS link (legacy subscriptions created before this field
        was introduced).
        """
        if not sub_id:
            return None
        base = (self.subscription_url_base or self.xui_url or "").rstrip("/")
        if not base:
            return None
        path = "/" + (self.subscription_path or "/sub/").strip("/") + "/"
        return f"{base}{path}{sub_id}"

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
