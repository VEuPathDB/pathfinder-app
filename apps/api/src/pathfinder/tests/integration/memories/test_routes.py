from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_list_memories_grouped_by_namespace(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
) -> None:
    await app_memory_store.put(
        user_id=authed_user_id,
        value=MemoryValue(
            kind="gene_set_note",
            name="a",
            summary="b",
            tags=[],
            content={},
            created_at=datetime.now(UTC),
        ),
    )
    resp = await authed_client.get("/api/v1/memories")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["geneSetNotes"]) == 1
    assert body["strategies"] == []


@pytest.mark.asyncio
async def test_delete_memory_writes_tombstone(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
) -> None:
    value = MemoryValue(
        kind="knowledge",
        name="t",
        summary="u",
        tags=[],
        content={"fact": "x"},
        created_at=datetime.now(UTC),
    )
    key = await app_memory_store.put(user_id=authed_user_id, value=value)
    resp = await authed_client.delete(f"/api/v1/memories/{key}?kind=knowledge")
    assert resp.status_code == 204
    remaining = await app_memory_store.list_all(
        user_id=authed_user_id, kind="knowledge"
    )
    assert remaining == []


@pytest.mark.asyncio
async def test_search_answers_with_the_stored_memories(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
) -> None:
    """The route ranks what the store holds. The ranking itself is the API's."""
    for summary in ["plasmodium drug targets", "cookie recipe"]:
        await app_memory_store.put(
            user_id=authed_user_id,
            value=MemoryValue(
                kind="knowledge",
                name=summary[:10],
                summary=summary,
                tags=[],
                content={},
                created_at=datetime.now(UTC),
            ),
        )
    resp = await authed_client.get("/api/v1/memories/search?q=antimalarial%20drugs")
    assert resp.status_code == 200
    hits = resp.json()["hits"]
    assert {hit["value"]["summary"] for hit in hits} == {
        "plasmodium drug targets",
        "cookie recipe",
    }
    assert all(hit["key"] for hit in hits)


@pytest.mark.asyncio
async def test_patch_memory_updates_fields(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
) -> None:
    value = MemoryValue(
        kind="knowledge",
        name="old_name",
        summary="s",
        tags=["one"],
        content={},
        created_at=datetime.now(UTC),
    )
    key = await app_memory_store.put(user_id=authed_user_id, value=value)
    resp = await authed_client.patch(
        f"/api/v1/memories/{key}?kind=knowledge",
        json={"name": "new_name", "tags": ["two"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["value"]["name"] == "new_name"
    assert body["value"]["tags"] == ["two"]


@pytest.mark.asyncio
async def test_a_case_lists_and_deletes_like_any_kind(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    app_memory_store: MemoryStore,
) -> None:
    """The kind a verified turn writes is reachable from the settings surface."""
    key = await app_memory_store.put(
        user_id=authed_user_id,
        value=MemoryValue(
            kind="case",
            name="find every kinase in P. falciparum",
            summary="142 results via GenesByGoTerm",
            tags=["plasmodb"],
            content={"case": "outcome", "root_count": 142},
            created_at=datetime.now(UTC),
        ),
    )
    listed = await authed_client.get("/api/v1/memories")
    assert listed.status_code == 200
    assert [item["key"] for item in listed.json()["cases"]] == [key]

    deleted = await authed_client.delete(f"/api/v1/memories/{key}?kind=case")
    assert deleted.status_code == 204
    assert await app_memory_store.list_all(user_id=authed_user_id, kind="case") == []
