from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from langgraph.runtime import Runtime

from pathfinder.ai.graph import nodes
from pathfinder.ai.models.mock.explore_arc import FIRST_LABEL, SECOND_LABEL
from pathfinder.services.conversations.message_ratings import TurnMemories
from pathfinder.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    SITE,
    explore_state,
    install_explore_doubles,
    run_explore,
    update_of,
)
from pathfinder.tests._support.recording_memory_store import RecordingMemoryStore
from pathfinder.tests._support.run_context import turn_runtime


@dataclass
class _Finalized:
    store: RecordingMemoryStore = field(default_factory=RecordingMemoryStore)
    writes: list[TurnMemories] = field(default_factory=list)
    compactions: int = 0


@pytest.fixture
def finalized(monkeypatch: pytest.MonkeyPatch) -> _Finalized:
    install_explore_doubles(monkeypatch)
    recorded = _Finalized()

    async def _no_turn_message(**kwargs: Any) -> None:
        del kwargs

    async def _write(turn: TurnMemories, **kwargs: Any) -> None:
        del kwargs
        recorded.writes.append(turn)

    async def _compact(**kwargs: Any) -> None:
        del kwargs
        recorded.compactions += 1

    monkeypatch.setattr(nodes, "write_turn_message", _no_turn_message)
    monkeypatch.setattr(nodes, "write_turn_memories", _write)
    monkeypatch.setattr(nodes, "compact_scratchpad", _compact)
    return recorded


async def test_finalize_after_an_explore_turn_writes_no_memory_and_keeps_its_state(
    finalized: _Finalized,
) -> None:
    state = explore_state(EXPLORE_PROMPT)
    explored = state.model_copy(update=update_of(await run_explore(state)))
    runtime = Runtime(
        context=turn_runtime(
            site_id=SITE, user_id=explored.user_id, memory_store=finalized.store
        )
    )

    command = await nodes.finalize_turn_node(explored, runtime)

    assert explored.domain.reading_labels() == [FIRST_LABEL, SECOND_LABEL]
    assert (finalized.writes, finalized.compactions, finalized.store.rows) == (
        [],
        0,
        {},
    )
    assert [command.update] == [None]
