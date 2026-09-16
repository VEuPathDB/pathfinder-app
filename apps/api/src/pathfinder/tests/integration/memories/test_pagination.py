"""Pagination: limit + offset query params + hasMore flag."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from httpx import AsyncClient


async def _seed(store: MemoryStore, user_id: UUID, n: int) -> list[str]:
    keys: list[str] = []
    for i in range(n):
        value = MemoryValue(
            kind="knowledge",
            name=f"item-{i:03d}",
            summary=f"summary for item {i}",
            tags=[],
            content={"idx": i},
            created_at=datetime.now(UTC),
        )
        keys.append(await store.put(user_id=user_id, value=value))
    return keys


@pytest.mark.asyncio
async def test_limit_caps_page_and_has_more_flips(
    authed_client: AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    await _seed(app_memory_store, authed_user_id, n=6)

    first = await authed_client.get("/api/v1/memories?limit=5&offset=0")
    assert first.status_code == 200
    body1 = first.json()
    assert len(body1["knowledge"]) == 5
    assert body1["pageSize"] == 5
    assert body1["offset"] == 0
    assert body1["hasMore"] is True, "5 of 6 rows returned - more available"

    second = await authed_client.get("/api/v1/memories?limit=5&offset=5")
    assert second.status_code == 200
    body2 = second.json()
    assert len(body2["knowledge"]) == 1
    assert body2["offset"] == 5
    assert body2["hasMore"] is False


@pytest.mark.asyncio
async def test_offset_returns_different_items_than_page_zero(
    authed_client: AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    """Offset must actually skip - no overlap between offset=0 and offset=N."""
    del db_cleaner, patch_app_db_engine
    seeded_keys = set(await _seed(app_memory_store, authed_user_id, n=8))

    page0 = (
        await authed_client.get(
            "/api/v1/memories?limit=4&offset=0",
        )
    ).json()
    page1 = (
        await authed_client.get(
            "/api/v1/memories?limit=4&offset=4",
        )
    ).json()

    keys0 = {item["key"] for item in page0["knowledge"]}
    keys1 = {item["key"] for item in page1["knowledge"]}
    assert len(keys0) == 4
    assert len(keys1) == 4
    assert keys0.isdisjoint(keys1), "offset page must not overlap offset=0"
    assert keys0 | keys1 == seeded_keys


@pytest.mark.asyncio
async def test_has_more_false_when_no_namespace_full(
    authed_client: AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    await _seed(app_memory_store, authed_user_id, n=3)

    resp = await authed_client.get("/api/v1/memories?limit=50")
    body = resp.json()
    assert len(body["knowledge"]) == 3
    assert body["hasMore"] is False
    assert body["pageSize"] == 50
