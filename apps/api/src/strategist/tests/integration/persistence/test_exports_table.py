from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select

from strategist.persistence.models import Export, User


@pytest.mark.asyncio
async def test_export_row_roundtrip(
    db_cleaner: None, patch_app_db_engine: None
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    export_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Export(
                id=export_id,
                user_id=user_id,
                filename="test.csv",
                content_type="text/csv",
                data=b"a,b,c\n1,2,3\n",
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        row = (
            await session.execute(select(Export).where(Export.id == export_id))
        ).scalar_one()
        assert row.filename == "test.csv"
        assert row.data == b"a,b,c\n1,2,3\n"
        assert row.user_id == user_id
