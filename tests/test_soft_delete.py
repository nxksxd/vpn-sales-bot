import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base
from bot.database.repositories.user import UserRepository


@pytest.mark.asyncio
async def test_soft_delete_hides_user_but_keeps_row() -> None:
    db_path = Path(tempfile.mkdtemp()) / "test_soft_delete.sqlite"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.get_or_create(100, username="u", first_name="U")

        # Soft delete hides the user from default lookups...
        assert await repo.soft_delete(100) is True
        assert await repo.get_by_telegram_id(100) is None
        # ...but the row is still there.
        assert await repo.get_by_telegram_id(100, include_deleted=True) is not None
        # ...and is excluded from broadcasts.
        assert 100 not in list(await repo.get_all_telegram_ids())

        # Re-engagement revives the account.
        await repo.get_or_create(100, username="u", first_name="U")
        assert await repo.get_by_telegram_id(100) is not None

    await engine.dispose()
