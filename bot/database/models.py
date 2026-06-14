"""SQLAlchemy ORM models for the VPN sales bot."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str] = mapped_column(String(10), default="ru")
    balance: Mapped[int] = mapped_column(Integer, default=0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    last_active: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    vpn_keys: Mapped[list["VpnKey"]] = relationship(
        back_populates="user", lazy="selectin"
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True
    )
    plan_type: Mapped[str] = mapped_column(String(50), nullable=False)
    price_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    starts_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True)
    xui_client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    xui_inbound_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vless_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traffic_limit_gb: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    vpn_key: Mapped[Optional["VpnKey"]] = relationship(
        back_populates="subscription", uselist=False, lazy="selectin"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    stars_payment_charge_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="transactions")


class VpnKey(Base):
    __tablename__ = "vpn_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True
    )
    xui_client_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    xui_inbound_id: Mapped[int] = mapped_column(Integer, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    vless_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )

    subscription: Mapped["Subscription"] = relationship(back_populates="vpn_key")
    user: Mapped["User"] = relationship(back_populates="vpn_keys")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    sent_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subscriptions.id"), nullable=True
    )
