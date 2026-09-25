"""A turn that ends on a card writes the reply the card call carries, then the card."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    RetryPromptPart,
    ToolCallPart,
)

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL
from pathfinder.tests.unit.ai.graph._approval_turn import (
    Collector,
    drive_lead,
    lead_deps,
    lead_state,
    scripted_model,
    writer,
)

__all__ = ["writer"]

ANALYSIS = (
    "The strategy is one INTERSECT of the signal peptide search and the 2 to 99 "
    "transmembrane domain search. The 2 to 99 range is the weak spot: it keeps "
    "single-pass and many-pass proteins alike."
)
PROPOSAL: dict[str, Any] = {
    "question": "Narrow the transmembrane range to one domain?",
    "proposedChanges": ["Set the transmembrane domain range to 1 to 1."],
}


def _proposing(replies: list[str], seen: list[list[ModelMessage]]) -> Any:
    """Each response is one proposal card carrying the next reply."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        seen.append(messages)
        turn = len(seen) - 1
        return ToolCallPart(
            tool_name=PROPOSAL_TOOL,
            args={**PROPOSAL, "reply": replies[turn]},
            tool_call_id=f"call_card_{turn}",
        )

    return scripted_model(_part)


async def _parked(
    monkeypatch: pytest.MonkeyPatch, writer: Collector, replies: list[str]
) -> list[list[ModelMessage]]:
    seen: list[list[ModelMessage]] = []
    monkeypatch.setattr(
        _lead_model, "get_mock_model", lambda: _proposing(replies, seen)
    )
    state = lead_state()
    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    assert capture.pending_approval is not None
    return seen


def _types(writer: Collector) -> list[str]:
    return [str(p["chunk"]["type"]) for p in writer.payloads if "chunk" in p]


async def test_the_reply_streams_before_the_approval_request(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _parked(monkeypatch, writer, [ANALYSIS])

    types = _types(writer)
    order = [
        types.index("text-start"),
        types.index("text-delta"),
        types.index("text-end"),
        types.index("tool-input-start"),
        types.index("tool-approval-request"),
    ]
    assert order == sorted(order)
    assert [c["delta"] for c in writer.chunks_of("text-delta")] == [ANALYSIS]


async def test_an_empty_reply_is_refused_before_any_card(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = await _parked(monkeypatch, writer, ["   ", ANALYSIS])

    assert len(seen) == 2
    refusals = [
        part.model_response()
        for message in seen[1]
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]
    assert len(refusals) == 1
    assert "reply" in refusals[0]
    assert [c["toolCallId"] for c in writer.chunks_of("tool-approval-request")] == [
        "call_card_1"
    ]
    assert [c["delta"] for c in writer.chunks_of("text-delta")] == [ANALYSIS]
