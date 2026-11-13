from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.tombstones import (
    TombstoneRepository,
    compute_content_hash,
)
from assistant_core.platform.db import async_session_factory

from strategist.persistence.models import User


def _value(content: dict[str, object]) -> MemoryValue:
    return MemoryValue(
        kind="knowledge",
        name="example",
        summary="s",
        tags=[],
        content=content,
        created_at=datetime.now(UTC),
    )


def test_content_hash_is_stable_across_dict_ordering() -> None:
    a = compute_content_hash({"x": 1, "y": 2})
    b = compute_content_hash({"y": 2, "x": 1})
    assert a == b


@pytest.mark.asyncio
async def test_tombstone_roundtrip_and_exists_check(
    db_cleaner: None, patch_app_db_engine: None
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()

    repo = TombstoneRepository(session_factory=async_session_factory)
    value = _value({"fact": "bradyzoite excluded"})
    assert not await repo.exists(user_id=user_id, value=value)

    await repo.tombstone(user_id=user_id, value=value, reason="user_deleted")
    assert await repo.exists(user_id=user_id, value=value)

    other_value = _value({"fact": "something else"})
    assert not await repo.exists(user_id=user_id, value=other_value)
