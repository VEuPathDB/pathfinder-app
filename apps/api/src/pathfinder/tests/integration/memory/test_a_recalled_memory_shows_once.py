"""The Lead's search_memory shows each memory it recalls on a card the first
time the conversation recalls it, with the date and the conversation that tell
two memories of one name apart."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore

from pathfinder.ai.conversation._turn_helpers import _extract_chunk
from pathfinder.ai.lead import lead_memory_tools
from pathfinder.ai.lead.lead_memory_tools import search_memory
from pathfinder.tests._support.run_context import (
    lead_run_context,
    run_context_for,
    turn_runtime,
)

_GOAL = "Find P. falciparum 3D7 genes with a signal peptide"
_FIRST, _SECOND = uuid4(), uuid4()


def _case(count: int, day: int, source: Any) -> MemoryValue:
    return MemoryValue(
        kind="case",
        name=_GOAL,
        summary=f"{_GOAL} reached {count} results",
        site_id="plasmodb",
        content={"goal": _GOAL, "root_count": count},
        source_conversation_id=source,
        created_at=datetime(2026, 9, day, tzinfo=UTC),
    )


async def test_a_recalled_memory_shows_once_with_what_tells_it_apart(
    monkeypatch: pytest.MonkeyPatch,
    app_memory_store: MemoryStore,
) -> None:
    held = lead_run_context()
    runtime = turn_runtime(
        memory_store=app_memory_store.store, user_id=held.deps.state.user_id
    )
    ctx = run_context_for(replace(held.deps, runtime=runtime))
    for value in (_case(3, 13, _FIRST), _case(18, 16, _SECOND)):
        await app_memory_store.put(user_id=ctx.deps.state.user_id, value=value)
    written: list[object] = []
    monkeypatch.setattr(lead_memory_tools, "get_stream_writer", lambda: written.append)

    await search_memory(ctx, query=_GOAL, kind="case")
    await search_memory(ctx, query=_GOAL, kind="case")

    cards = [
        chunk["data"]["memories"]
        for payload in written
        if (chunk := _extract_chunk(payload))
        and chunk["type"] == "data-memory-retrieved"
    ]
    assert len(cards) == 1
    assert sorted(
        (row["createdAt"][:10], row["name"], row["sourceConversationId"])
        for row in cards[0]
    ) == [
        ("2026-09-13", _GOAL, str(_FIRST)),
        ("2026-09-16", _GOAL, str(_SECOND)),
    ]
