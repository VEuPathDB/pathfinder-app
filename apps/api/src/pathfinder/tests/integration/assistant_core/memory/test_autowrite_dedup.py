"""Regression: repeated autowrites produce one row per (user, kind, key), not N."""

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
async def test_strategy_autowrite_is_idempotent(
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
        goal="q",
        interpreted_goal="Malaria",
        criteria=[Criterion(id="c1", text="malaria", search_name="GenesByGoTerm")],
    )
    state = PipelineState(
        conversation_id=conversation_id,
        user_id=user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="q",
        domain=StrategyDomainState(operational_spec=spec),
    )

    async with lifespan_memory_store(database_url) as raw:
        store = MemoryStore(store=raw)
        tombstones = TombstoneRepository(session_factory=async_session_factory)
        for _ in range(3):
            await auto_write_memories(
                store=store,
                tombstones=tombstones,
                user_id=state.user_id,
                candidates=await collect_turn_memory_candidates(state),
            )
        strategies = await store.list_all(user_id=user_id, kind="strategy")
        assert len(strategies) == 1, (
            f"expected 1 strategy after 3 autowrites, got {len(strategies)}"
        )


@pytest.mark.asyncio
async def test_gene_set_autowrite_is_idempotent(
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
        user_prompt="q",
        domain=StrategyDomainState(created_gene_set_ids=["gs-same-id"]),
    )

    async with lifespan_memory_store(database_url) as raw:
        store = MemoryStore(store=raw)
        tombstones = TombstoneRepository(session_factory=async_session_factory)
        for _ in range(3):
            await auto_write_memories(
                store=store,
                tombstones=tombstones,
                user_id=state.user_id,
                candidates=await collect_turn_memory_candidates(state),
            )
        sets = await store.list_all(user_id=user_id, kind="gene_set")
        assert len(sets) == 1
