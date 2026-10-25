from __future__ import annotations

import os
from uuid import uuid4

import pytest
from assistant_core.memory.autowrite import auto_write_memories
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.store import MemoryStore
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.platform.db import async_session_factory

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.memory_candidates import collect_memory_candidates
from pathfinder.domain.strategy.build_outcome import BuiltCounts
from pathfinder.persistence.models import User


@pytest.mark.asyncio
async def test_a_turn_never_writes_a_preference_the_researcher_did_not_approve(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="another",
    )

    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw_store:
        mem_store = MemoryStore(store=raw_store)
        await auto_write_memories(
            store=mem_store,
            tombstones=TombstoneRepository(session_factory=async_session_factory),
            user_id=state.user_id,
            candidates=collect_memory_candidates(state, counts=BuiltCounts()),
        )
        preferences = await mem_store.list_all(user_id=user_id, kind="preference")

    assert preferences == []
