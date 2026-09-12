from __future__ import annotations

import os
from uuid import uuid4

import pytest
from assistant_core.memory.autowrite import auto_write_memories
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.store import MemoryStore
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.platform.db import async_session_factory

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.memory_candidates import collect_turn_memory_candidates
from pathfinder.persistence.models import User


@pytest.mark.asyncio
async def test_auto_write_gene_sets(
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
        site_id="toxodb",
        mode="strategy",
        user_prompt="toxo bradyzoite",
        domain=StrategyDomainState(
            created_gene_sets=[
                CreatedGeneSet(id="gs-abc-123", name="kinase hits", gene_count=2)
            ]
        ),
    )

    async with lifespan_memory_store(database_url) as raw_store:
        mem_store = MemoryStore(store=raw_store)
        tombstones = TombstoneRepository(session_factory=async_session_factory)
        written = await auto_write_memories(
            store=mem_store,
            tombstones=tombstones,
            user_id=state.user_id,
            candidates=await collect_turn_memory_candidates(state),
        )
        assert written >= 1
        sets = await mem_store.list_all(user_id=user_id, kind="gene_set_note")
        assert len(sets) == 1
        assert sets[0].value.content["gene_set_id"] == "gs-abc-123"
