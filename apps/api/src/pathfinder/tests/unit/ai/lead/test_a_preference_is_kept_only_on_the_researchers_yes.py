from __future__ import annotations

import dataclasses

import pytest
from pydantic_ai import ApprovalRequired, DeferredToolRequests
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.lead.lead_memory_tools import ask_about_the_preferences, remember
from pathfinder.domain.memory import MemoryKind
from pathfinder.tests._support.recording_memory_store import RecordingMemoryStore
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.lead.conftest import ChunkCollector

_QUESTION = (
    "Remember in your later conversations: Default organism: "
    "Always use Plasmodium falciparum 3D7?"
)


async def _remember(
    store: RecordingMemoryStore, kind: MemoryKind, *, approved: bool
) -> None:
    ctx = lead_run_context(tool_call_id="call_remember")
    ctx.deps.runtime = dataclasses.replace(ctx.deps.runtime, memory_store=store)
    ctx.tool_call_approved = approved
    await remember(
        ctx,
        kind=kind,
        name="Default organism",
        summary="Always use Plasmodium falciparum 3D7",
        content={"organism": "Plasmodium falciparum 3D7"},
    )


async def test_a_preference_waits_for_the_researcher() -> None:
    store = RecordingMemoryStore()

    with pytest.raises(ApprovalRequired):
        await _remember(store, "preference", approved=False)

    assert store.rows == {}


async def test_an_approved_preference_is_stored() -> None:
    store = RecordingMemoryStore()

    await _remember(store, "preference", approved=True)

    assert [payload["summary"] for payload in store.rows.values()] == [
        "Always use Plasmodium falciparum 3D7"
    ]


@pytest.mark.parametrize("kind", ["knowledge", "gene_set_note", "strategy", "case"])
async def test_a_kind_that_is_not_pinned_is_stored_at_once(kind: MemoryKind) -> None:
    store = RecordingMemoryStore()

    await _remember(store, kind, approved=False)

    assert len(store.rows) == 1


def _parked(tool_name: str, args: dict[str, object]) -> DeferredToolRequests:
    return DeferredToolRequests(
        approvals=[
            ToolCallPart(tool_name=tool_name, args=args, tool_call_id="call_remember")
        ]
    )


def test_a_parked_preference_asks_with_what_it_would_keep() -> None:
    writer = ChunkCollector()

    ask_about_the_preferences(
        _parked(
            "remember",
            {
                "kind": "preference",
                "name": "Default organism",
                "summary": "Always use Plasmodium falciparum 3D7",
                "content": {},
            },
        ),
        writer,
    )

    assert [
        (s["toolCallId"], s["summary"]) for s in writer.data_of("data-tool-summary")
    ] == [("call_remember", _QUESTION)]


def test_another_parked_card_is_not_asked_here() -> None:
    writer = ChunkCollector()

    ask_about_the_preferences(_parked("clear_strategy", {"confirm": True}), writer)

    assert writer.data_of("data-tool-summary") == []
