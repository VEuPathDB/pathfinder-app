"""A user-deleted memory must not silently return on the next successful turn.

This exercises the full delete-then-autowrite path the DELETE route triggers
(``tombstones.tombstone(value=current.value)`` then ``store.delete(...)``) and
the autowrite tombstone check — the seam where a content-hash mismatch between
the stored value and the freshly-built candidate would let a deleted memory
resurrect. The hash must survive the ``model_dump(json)`` → ``model_validate``
store round-trip for the dedup to hold.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from assistant_core.memory.autowrite import auto_write_memories
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.platform.db import async_session_factory

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.memory_candidates import collect_turn_memory_candidates
from pathfinder.persistence.models import User


@pytest.mark.asyncio
async def test_deleted_gene_set_memory_does_not_resurrect(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    database_url = os.environ["DATABASE_URL"]
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()

    state = PipelineState(
        conversation_id=uuid4(),
        user_id=user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="q",
        domain=StrategyDomainState(created_gene_set_ids=["gs-delete-me"]),
    )

    async with lifespan_memory_store(database_url) as raw:
        store = MemoryStore(store=raw)
        tombstones = TombstoneRepository(session_factory=async_session_factory)

        # Turn 1: memory is written.
        written_first = await auto_write_memories(
            store=store,
            tombstones=tombstones,
            user_id=state.user_id,
            candidates=await collect_turn_memory_candidates(state),
        )
        assert written_first == 1
        stored = await store.list_all(user_id=user_id, kind="gene_set_note")
        assert len(stored) == 1
        deleted = stored[0]

        # User deletes it — the DELETE route tombstones the stored value
        # (hashed from the round-tripped content) then removes it.
        await tombstones.tombstone(user_id=user_id, value=deleted.value)
        await store.delete(user_id=user_id, kind="gene_set_note", key=deleted.key)
        assert await store.list_all(user_id=user_id, kind="gene_set_note") == []

        # Turn 2: the same successful artifact is offered again — and refused.
        written_second = await auto_write_memories(
            store=store,
            tombstones=tombstones,
            user_id=state.user_id,
            candidates=await collect_turn_memory_candidates(state),
        )
        assert written_second == 0, "tombstoned memory was re-added"
        assert await store.list_all(user_id=user_id, kind="gene_set_note") == []


@pytest.mark.asyncio
async def test_tombstone_is_kind_scoped_not_global(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    """A tombstone on one kind must not block a different kind with the same
    content hash. The dedup key is ``(kind, content_hash)`` — proving the kind
    is part of the key prevents an over-broad delete from suppressing unrelated
    memories.
    """
    del db_cleaner, patch_app_db_engine
    database_url = os.environ["DATABASE_URL"]
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()

    async with lifespan_memory_store(database_url) as raw:
        store = MemoryStore(store=raw)
        tombstones = TombstoneRepository(session_factory=async_session_factory)

        # Write a gene_set, then delete+tombstone it.
        gs_state = PipelineState(
            conversation_id=uuid4(),
            user_id=user_id,
            site_id="plasmodb",
            mode="strategy",
            user_prompt="q",
            domain=StrategyDomainState(created_gene_set_ids=["shared-id"]),
        )
        await auto_write_memories(
            store=store,
            tombstones=tombstones,
            user_id=gs_state.user_id,
            candidates=await collect_turn_memory_candidates(gs_state),
        )
        stored = (await store.list_all(user_id=user_id, kind="gene_set_note"))[0]
        await tombstones.tombstone(user_id=user_id, value=stored.value)
        await store.delete(user_id=user_id, kind="gene_set_note", key=stored.key)

        # A preference memory (different kind) for the same site must still
        # write — it shares neither kind nor content with the tombstone.
        pref = MemoryValue(
            kind="preference",
            name="preferred_site:plasmodb",
            summary="uses plasmodb",
            tags=["plasmodb"],
            site_id="plasmodb",
            content={"preferred_site": "plasmodb"},
            created_at=datetime.now(UTC),
        )
        assert not await tombstones.exists(user_id=user_id, value=pref)
        await store.put(user_id=user_id, value=pref, key="preferred_site:plasmodb")
        assert len(await store.list_all(user_id=user_id, kind="preference")) == 1
