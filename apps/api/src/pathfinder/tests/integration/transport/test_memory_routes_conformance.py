"""The memories routes the conformance app serves, over a seeded store."""

from __future__ import annotations

from uuid import UUID

import httpx
from assistant_core.memory.store import MemoryStore
from fastapi import FastAPI

from pathfinder.platform.security import create_user_token
from pathfinder.tests._support.memory_store_double import (
    LoopFreeMemoryStore,
    seed_key,
)

# The listing's buckets, in the order the router fills them from MEMORY_KINDS.
_MEMORY_BUCKETS = (
    "geneSetNotes",
    "strategies",
    "preferences",
    "knowledge",
    "cases",
)


def test_the_conformance_double_covers_the_store_surface() -> None:
    """Every call MemoryStore offers is answered by the conformance double."""
    offered = {
        name
        for name, member in vars(MemoryStore).items()
        if not name.startswith("_") and callable(member)
    }
    assert offered == {"put", "get", "delete", "list_all", "semantic_search"}
    assert offered - set(vars(LoopFreeMemoryStore)) == set()


async def test_the_fuzzed_user_holds_a_memory_of_every_kind(
    patched_app: tuple[FastAPI, UUID],
    seeded_memories: LoopFreeMemoryStore,
) -> None:
    """The memories routes serve items, so the fuzz validates a serialized one."""
    del seeded_memories
    app, user_id = patched_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        client.cookies.set("pathfinder-auth", create_user_token(user_id))
        listed = await client.get(
            "/api/v1/memories", params={"limit": "50", "offset": "0"}
        )
        searched = await client.get("/api/v1/memories/search", params={"q": "one"})
        edited = await client.patch(
            f"/api/v1/memories/{seed_key('knowledge')}",
            params={"kind": "knowledge"},
            json={"summary": "an edited summary"},
        )
        removed = await client.delete(
            f"/api/v1/memories/{seed_key('knowledge')}",
            params={"kind": "knowledge"},
        )
        after = await client.get(
            "/api/v1/memories", params={"limit": "50", "offset": "0"}
        )

    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert [len(body[bucket]) for bucket in _MEMORY_BUCKETS] == [1, 1, 1, 1, 1]
    seeded = body["knowledge"][0]
    assert seeded["key"] == seed_key("knowledge")
    assert seeded["value"]["kind"] == "knowledge"
    assert seeded["value"]["siteId"] == "plasmodb"
    assert seeded["value"]["createdAt"] == "2026-01-01T00:00:00Z"
    assert seeded["value"]["content"] == {"kind": "knowledge", "count": 1}

    assert searched.status_code == 200, searched.text
    assert len(searched.json()["hits"]) == 5

    assert edited.status_code == 200, edited.text
    assert edited.json()["value"]["summary"] == "an edited summary"
    assert edited.json()["value"]["name"] == "a knowledge the conformance run reads"

    assert removed.status_code == 204, removed.text
    assert after.json()["knowledge"] == []


async def test_memory_endpoints_have_store_in_conformance_app(
    patched_app: tuple[FastAPI, UUID],
) -> None:
    app, user_id = patched_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        client.cookies.set("pathfinder-auth", create_user_token(user_id))
        listed = await client.get(
            "/api/v1/memories", params={"limit": "1", "offset": "0"}
        )
        searched = await client.get("/api/v1/memories/search", params={"q": "x"})
        missing = await client.delete(
            "/api/v1/memories/nope", params={"kind": "knowledge"}
        )
    assert listed.status_code == 200, listed.text
    assert searched.status_code == 200, searched.text
    assert missing.status_code == 404, missing.text
    assert missing.headers["content-type"].startswith("application/problem+json")
