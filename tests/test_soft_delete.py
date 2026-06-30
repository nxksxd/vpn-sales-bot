import datetime
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
        user = await repo.get_or_create(100, username="u", first_name="U")
        active_user = await repo.get_or_create(
            200, username="active", first_name="Active"
        )
        active_user.referral_code = "ACTIVE200"
        active_user.last_active = datetime.datetime.utcnow()
        user.referral_code = "DELETED100"
        user.is_banned = True
        user.trial_used = False
        user.last_active = datetime.datetime.utcnow()
        await session.commit()

        # Soft delete hides the user from default lookups...
        assert await repo.soft_delete(100) is True
        assert await repo.get_by_telegram_id(100) is None
        # ...but the row is still there.
        assert await repo.get_by_telegram_id(100, include_deleted=True) is not None
        # ...and is excluded from all user-facing/admin collections.
        assert 100 not in list(await repo.get_all_telegram_ids())
        assert [u.telegram_id for u in await repo.search_users("u")] == []
        assert await repo.get_by_referral_code("DELETED100") is None
        assert await repo.count_all() == 1
        assert await repo.count_active() == 1
        assert await repo.count_banned() == 0
        assert await repo.count_created_since(datetime.datetime.utcnow()) == 0
        assert 100 not in list(await repo.get_segmented_users("trial_unused"))

        # Mutations should not silently affect a soft-deleted account.
        assert await repo.update_balance(100, 100) is None
        assert await repo.set_balance(100, 100) is None
        assert await repo.set_banned(100, False) is None

        # Re-engagement revives the account.
        await repo.get_or_create(100, username="u", first_name="U")
        assert await repo.get_by_telegram_id(100) is not None

    await engine.dispose()
