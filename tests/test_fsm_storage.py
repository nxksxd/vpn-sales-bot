"""Tests for FSM storage selection."""

from __future__ import annotations

from aiogram.fsm.storage.memory import MemoryStorage

from bot import main


def test_build_fsm_storage_defaults_to_memory(monkeypatch):
    monkeypatch.setattr(main.settings, "redis_url", "")

    storage = main.build_fsm_storage()

    assert isinstance(storage, MemoryStorage)


def test_build_fsm_storage_uses_redis_when_configured(monkeypatch):
    from aiogram.fsm.storage.redis import RedisStorage

    monkeypatch.setattr(main.settings, "redis_url", "redis://localhost:6379/0")

    storage = main.build_fsm_storage()

    assert isinstance(storage, RedisStorage)
