"""Tests for safe YooKassa secret helper."""

from __future__ import annotations

from scripts.set_yookassa_secret import _set_env_value


def test_set_env_value_replaces_existing_key_without_touching_others() -> None:
    lines = [
        "YOOKASSA_SHOP_ID=1396584",
        "YOOKASSA_SECRET_KEY=",
        "YOOKASSA_WEBHOOK_PORT=8080",
    ]

    updated = _set_env_value(lines, "YOOKASSA_SECRET_KEY", "test_secret")

    assert updated == [
        "YOOKASSA_SHOP_ID=1396584",
        "YOOKASSA_SECRET_KEY=test_secret",
        "YOOKASSA_WEBHOOK_PORT=8080",
    ]


def test_set_env_value_appends_missing_key() -> None:
    lines = ["YOOKASSA_SHOP_ID=1396584"]

    updated = _set_env_value(lines, "YOOKASSA_SECRET_KEY", "test_secret")

    assert updated == [
        "YOOKASSA_SHOP_ID=1396584",
        "",
        "YOOKASSA_SECRET_KEY=test_secret",
    ]
