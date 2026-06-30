import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base, PromoCode, ServerRegion
from bot.services.subscription_use_cases import SubscriptionUseCases


class _DummyXUI:
    pass


@pytest.mark.asyncio
async def test_subscription_use_cases_resolve_region_and_promo() -> None:
    db_path = Path(tempfile.mkdtemp()) / "test_subscription_uc.sqlite"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(ServerRegion(code="nl", label="Netherlands", server_address="nl.example.com", inbound_id=7, is_active=True))
        session.add(PromoCode(code="SAVE20", discount_percent=20, is_active=True, usage_limit=10, used_count=0))
        await session.commit()

    async with session_factory() as session:
        uc = SubscriptionUseCases(session, _DummyXUI())
        region = await uc.resolve_region("nl")
        promo = await uc.resolve_promo("SAVE20")
        assert region is not None
        assert region.label == "Netherlands"
        assert promo is not None
        assert promo.discount_percent == 20

    await engine.dispose()
