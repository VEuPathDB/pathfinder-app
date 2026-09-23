"""The reply a Lead writes beside a card is held to the turn contract before
the card reaches the researcher."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.tests.unit.ai.graph._approval_turn import (
    Collector,
    drive_lead,
    lead_deps,
    lead_state,
    writer,
)

__all__ = ["writer"]

SEARCH = "Orthology Phylogenetic Profile"
LEAVES_IT_OUT = (
    "The strategy now returns 4 genes, and the check found two limitations. "
    "I can tighten both."
)
NAMES_IT = (
    f"I added {SEARCH} for the three-species orthologs; the strategy returns 4 "
    "genes, and the check found two limitations. I can tighten both."
)
CARD_ARGS: dict[str, Any] = {
    "question": "Refine the strategy with the two checks?",
    "proposedChanges": ["Require 1:1:1 syntenic orthologs in all three species"],
}


def _card_turn(replies: list[str], seen: list[list[ModelMessage]]) -> FunctionModel:
    """Each response writes the next reply and ends on a proposal card."""

    def _next(messages: list[ModelMessage]) -> tuple[str, str]:
        seen.append(messages)
        turn = len(seen) - 1
        return replies[turn], f"call_card_{turn}"

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        text, call_id = _next(messages)
        return ModelResponse(
            parts=[
                TextPart(content=text),
                ToolCallPart(
                    tool_name=PROPOSAL_TOOL, args=CARD_ARGS, tool_call_id=call_id
                ),
            ]
        )

    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del info
        text, call_id = _next(messages)
        yield text
        yield {
            1: DeltaToolCall(
                name=PROPOSAL_TOOL,
                json_args=json.dumps(CARD_ARGS),
                tool_call_id=call_id,
            )
        }

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


async def _built_turn_ending_on_a_card(
    monkeypatch: pytest.MonkeyPatch,
    writer: Collector,
    replies: list[str],
) -> tuple[list[list[ModelMessage]], Any]:
    seen: list[list[ModelMessage]] = []
    monkeypatch.setattr(
        _lead_model, "get_mock_model", lambda: _card_turn(replies, seen)
    )
    state = lead_state()
    deps = lead_deps(state)
    state.record_build(BuildOutcome(pushed_step_ids=["s1", "s2"], root_count=4))
    state.turn_markers.verified = True
    state.turn_markers.record_added_searches(
        [
            AddedSearch(
                step_id="s2",
                search_display_name=SEARCH,
                criterion_text="orthologs in three species",
            )
        ]
    )
    capture = await drive_lead(state=state, deps=deps, writer=writer)
    return seen, capture


def _written_text(writer: Collector) -> str:
    return "".join(chunk["delta"] for chunk in writer.chunks_of("text-delta"))


def _cards_on_the_wire(writer: Collector) -> list[str]:
    return [
        chunk["toolCallId"]
        for chunk in writer.chunks_of("tool-input-start")
        if chunk["toolName"] == PROPOSAL_TOOL
    ]


async def test_a_card_whose_reply_leaves_out_the_added_search_is_asked_once(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen, capture = await _built_turn_ending_on_a_card(
        monkeypatch, writer, [LEAVES_IT_OUT, NAMES_IT]
    )

    assert len(seen) == 2
    denials = [
        str(part.content)
        for message in seen[1]
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_call_id == "call_card_0"
    ]
    assert len(denials) == 1
    denial = denials[0]
    assert "This reply does not match what the turn did:" in denial
    assert SEARCH in denial
    assert capture.pending_approval is not None
    assert capture.pending_approval.tool_call_id == "call_card_1"
    assert _written_text(writer) == NAMES_IT
    assert _cards_on_the_wire(writer) == ["call_card_1"]
    assert [c["toolCallId"] for c in writer.chunks_of("tool-approval-request")] == [
        "call_card_1"
    ]
    assert writer.chunks_of("tool-output-denied") == []


async def test_a_card_whose_reply_matches_the_turn_parks_in_one_run(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen, capture = await _built_turn_ending_on_a_card(monkeypatch, writer, [NAMES_IT])

    assert len(seen) == 1
    assert capture.pending_approval is not None
    assert capture.pending_approval.tool_call_id == "call_card_0"
    assert _written_text(writer) == NAMES_IT
    assert _cards_on_the_wire(writer) == ["call_card_0"]
    assert [c["toolCallId"] for c in writer.chunks_of("tool-approval-request")] == [
        "call_card_0"
    ]
