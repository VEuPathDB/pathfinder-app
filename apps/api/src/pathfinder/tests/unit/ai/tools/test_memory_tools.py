"""What ``remember`` writes: one row per standing preference, many per case."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry, RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.memory_tools import remember
from pathfinder.domain.memory import MemoryKind
from pathfinder.tests._support.recording_memory_store import RecordingMemoryStore
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


async def _remember(ctx: RunContext[AgentDeps], kind: MemoryKind, content: str) -> str:
    return returned(
        await remember(
            ctx,
            kind=kind,
            name="Default organism",
            summary="the organism a turn assumes",
            content={"organism": content},
        ),
        str,
    )


def _one_user(store: RecordingMemoryStore) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    ctx.deps.memory_store = store
    return ctx


async def test_a_second_preference_of_one_name_replaces_the_first() -> None:
    store = RecordingMemoryStore()
    ctx = _one_user(store)

    first = await _remember(ctx, "preference", "P. falciparum 3D7")
    second = await _remember(ctx, "preference", "Plasmodium berghei ANKA")

    assert len(store.rows) == 1
    (payload,) = store.rows.values()
    assert payload["content"] == {"organism": "Plasmodium berghei ANKA"}
    assert first.startswith("Stored")
    assert second.startswith("Updated")


async def test_two_cases_of_one_name_are_both_kept() -> None:
    store = RecordingMemoryStore()
    ctx = _one_user(store)

    await _remember(ctx, "case", "P. falciparum 3D7")
    await _remember(ctx, "case", "Plasmodium berghei ANKA")

    assert len(store.rows) == 2


async def test_a_preference_with_no_name_is_sent_back_to_the_model() -> None:
    """A key derived from nothing would be one bucket for every such name."""
    ctx = _one_user(RecordingMemoryStore())

    with pytest.raises(ModelRetry, match="name"):
        await remember(
            ctx,
            kind="preference",
            name="???",
            summary="the organism a turn assumes",
            content={"organism": "Plasmodium berghei ANKA"},
        )
