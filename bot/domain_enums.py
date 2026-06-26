from __future__ import annotations

from enum import StrEnum


class SubscriptionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    GRACE_PERIOD = "grace_period"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class TransactionType(StrEnum):
    TOPUP = "topup"
    PURCHASE = "purchase"
    REFERRAL_BONUS = "referral_bonus"
    ADMIN_ADJUSTMENT = "admin_adjustment"
    BALANCE_DEBIT_ADJUSTMENT = "balance_debit_adjustment"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class AuditAction(StrEnum):
    USER_BALANCE_CHANGED = "user_balance_changed"
    USER_BANNED = "user_banned"
    USER_UNBANNED = "user_unbanned"
    USER_MESSAGE_SENT = "user_message_sent"
    KEY_REGENERATED = "key_regenerated"
    KEY_DEACTIVATED = "key_deactivated"
    KEY_REACTIVATED = "key_reactivated"
    TRAFFIC_RESET = "traffic_reset"
    SETTINGS_CHANGED = "settings_changed"
    SUBSCRIPTION_EXTENDED = "subscription_extended"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    BROADCAST_SENT = "broadcast_sent"
