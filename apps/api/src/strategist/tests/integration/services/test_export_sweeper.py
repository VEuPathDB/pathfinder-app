from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from sqlalchemy import func, select

from strategist.persistence.models import Export, User
from strategist.services.export.sweeper import sweep_expired_exports


@pytest.mark.asyncio
async def test_sweeper_deletes_only_expired(
    db_cleaner: None, patch_app_db_engine: None
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Export(
                id=uuid4(),
                user_id=user_id,
                filename="old.csv",
                content_type="text/csv",
                data=b"x",
                expires_at=now - timedelta(minutes=1),
            )
        )
        session.add(
            Export(
                id=uuid4(),
                user_id=user_id,
                filename="fresh.csv",
                content_type="text/csv",
                data=b"y",
                expires_at=now + timedelta(minutes=5),
            )
        )
        await session.commit()

    deleted = await sweep_expired_exports()
    assert deleted == 1

    async with async_session_factory() as session:
        remaining = (
            await session.execute(select(func.count()).select_from(Export))
        ).scalar_one()
        assert remaining == 1
