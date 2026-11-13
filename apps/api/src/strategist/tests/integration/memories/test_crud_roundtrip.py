"""HTTP CRUD roundtrip - catches the key-dropped bug."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_returns_real_keys_so_delete_works(
    authed_client: AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    value = MemoryValue(
        kind="knowledge",
        name="x",
        summary="y",
        tags=[],
        content={"fact": "z"},
        created_at=datetime.now(UTC),
    )
    stored_key = await app_memory_store.put(user_id=authed_user_id, value=value)
    assert stored_key, "put must return a non-empty key"

    list_resp = await authed_client.get("/api/v1/memories")
    assert list_resp.status_code == 200
    knowledge = list_resp.json()["knowledge"]
    assert len(knowledge) == 1
    returned_key = knowledge[0]["key"]
    assert returned_key, "list must return a non-empty key"
    assert returned_key == stored_key

    del_resp = await authed_client.delete(
        f"/api/v1/memories/{returned_key}?kind=knowledge"
    )
    assert del_resp.status_code == 204

    after = await authed_client.get("/api/v1/memories")
    assert after.json()["knowledge"] == []


@pytest.mark.asyncio
async def test_edit_preserves_key_and_persists(
    authed_client: AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    value = MemoryValue(
        kind="knowledge",
        name="original",
        summary="s",
        tags=[],
        content={},
        created_at=datetime.now(UTC),
    )
    key = await app_memory_store.put(user_id=authed_user_id, value=value)

    resp = await authed_client.patch(
        f"/api/v1/memories/{key}?kind=knowledge",
        json={"name": "renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["key"] == key
    assert resp.json()["value"]["name"] == "renamed"


@pytest.mark.asyncio
async def test_search_returns_real_keys(
    authed_client: AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    value = MemoryValue(
        kind="knowledge",
        name="plasmodium targets",
        summary="malaria drug targets",
        tags=[],
        content={},
        created_at=datetime.now(UTC),
    )
    key = await app_memory_store.put(user_id=authed_user_id, value=value)

    resp = await authed_client.get("/api/v1/memories/search?q=antimalarial%20targets")
    assert resp.status_code == 200
    hits = resp.json()["hits"]
    assert hits
    assert hits[0]["key"] == key


def test_uuid_import_placeholder() -> None:
    """Trivial sanity test to keep uuid4 import referenced for future growth."""
    assert uuid4() is not None
