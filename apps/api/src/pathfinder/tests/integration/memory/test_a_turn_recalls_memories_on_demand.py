"""A fresh turn pins only the standing memories, the researcher's preferences,
and counts the rest so the Lead knows what it can recall on demand."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from langgraph.runtime import Runtime

from pathfinder.ai.graph._lead_turn import memory_index, retrieve_memories
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database

_USER = uuid4()


def _memory(kind: str, name: str, site_id: str | None = "plasmodb") -> MemoryValue:
    return MemoryValue(
        kind=kind,
        name=name,
        summary=name,
        content={},
        site_id=site_id,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )


async def _runtime(memories: MemoryStore) -> Runtime[Context]:
    for value in (
        _memory("preference", "Default organism", site_id=None),
        _memory("strategy", "Secreted kinases"),
        _memory("case", "Signal peptide and two transmembrane domains"),
        _memory("strategy", "Toxoplasma cyst wall", site_id="toxodb"),
    ):
        await memories.put(user_id=_USER, value=value)
    return Runtime(
        context=Context(
            site_id="plasmodb",
            user_id=_USER,
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
            memory_store=memories.store,
        )
    )


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=_USER,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find secreted kinases like last time.",
    )


async def test_a_fresh_turn_pins_only_the_standing_memories(
    app_memory_store: MemoryStore,
) -> None:
    recalled = await retrieve_memories(_state(), await _runtime(app_memory_store))

    assert [s.value.name for s in recalled] == ["Default organism"]


async def test_the_turn_counts_what_it_can_recall_on_this_site(
    app_memory_store: MemoryStore,
) -> None:
    runtime = await _runtime(app_memory_store)

    assert await memory_index(_state(), runtime) == {"strategy": 1, "case": 1}
