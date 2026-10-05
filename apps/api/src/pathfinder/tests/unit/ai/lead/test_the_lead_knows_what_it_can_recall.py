"""The Lead's briefing names how many memories of each kind it can recall, and
the Lead recalls them with search_memory."""

from __future__ import annotations

from pathfinder.ai.lead.lead_pins import pinned_memory_index
from pathfinder.tests._support.run_context import lead_run_context


def test_no_memory_to_recall_pins_nothing() -> None:
    assert [pinned_memory_index(lead_run_context())] == [None]


def test_the_index_names_each_kind_and_how_to_recall_it() -> None:
    ctx = lead_run_context()
    ctx.deps.state.domain.memory_index = {"strategy": 12, "case": 3}

    assert pinned_memory_index(ctx) == "\n".join(
        [
            "## What you can recall about this user",
            (
                "Memories of this user's other conversations, not read into this "
                "turn: 12 strategy, 3 case. Call search_memory(query, kind) when the "
                "request points at earlier work or what you know of this user would "
                "change the answer."
            ),
        ]
    )
