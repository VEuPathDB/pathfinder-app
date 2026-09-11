from __future__ import annotations

import os
from uuid import uuid4

import pytest
from assistant_core.memory.autowrite import auto_write_memories
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.store import MemoryStore
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.platform.db import async_session_factory

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.memory_candidates import collect_turn_memory_candidates
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.persistence.models import User


@pytest.mark.asyncio
async def test_auto_write_persists_strategy_on_verification_complete(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    database_url = os.environ["DATABASE_URL"]
    user_id = uuid4()
    conversation_id = uuid4()

    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()

    spec = OperationalSpec(
        goal="malaria transporters",
        interpreted_goal="Malaria transporters",
        organism_scope="Plasmodium falciparum",
        criteria=[
            Criterion(id="c1", text="transporters", search_name="GenesByGoTerm"),
        ],
    )
    state = PipelineState(
        conversation_id=conversation_id,
        user_id=user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="malaria transporters",
        domain=StrategyDomainState(operational_spec=spec),
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
        strategies = await mem_store.list_all(user_id=user_id, kind="strategy")
        assert len(strategies) == 1
        assert strategies[0].value.site_id == "plasmodb"
