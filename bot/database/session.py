"""Async database session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings
from bot.database.models import Base

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Safe migration in separate transaction (works for both SQLite and PostgreSQL)
    from sqlalchemy import text

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN auto_renew BOOLEAN DEFAULT 1")
            )
    except Exception:
        pass  # Column already exists


async def close_db() -> None:
    await engine.dispose()
