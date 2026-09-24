"""The reply a Lead writes beside a card is held to the turn contract before
the card reaches the researcher."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.tests.unit.ai.graph._approval_turn import (
    LEAD_FINAL,
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
CARD = "call_card"
DELETE = "call_delete"
CARD_ARGS: dict[str, Any] = {
    "question": "Refine the strategy with the two checks?",
    "proposedChanges": ["Require 1:1:1 syntenic orthologs in all three species"],
}


def _scripted(
    parts_for: Callable[[list[ModelMessage]], list[TextPart | ToolCallPart]],
) -> FunctionModel:
    """A Lead whose responses stream their text before their calls."""

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        return ModelResponse(parts=parts_for(messages))

    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del info
        calls: dict[int, DeltaToolCall] = {}
        for index, part in enumerate(parts_for(messages)):
            if isinstance(part, TextPart):
                yield part.content
            else:
                calls[index] = DeltaToolCall(
                    name=part.tool_name,
                    json_args=part.args_as_json_str(),
                    tool_call_id=part.tool_call_id,
                )
        yield calls

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


def _card_turn(replies: list[str], seen: list[list[ModelMessage]]) -> FunctionModel:
    """Each response writes the next reply and ends on a proposal card."""

    def _parts(messages: list[ModelMessage]) -> list[TextPart | ToolCallPart]:
        seen.append(messages)
        turn = len(seen) - 1
        return [
            TextPart(content=replies[turn]),
            ToolCallPart(
                tool_name=PROPOSAL_TOOL,
                args=CARD_ARGS,
                tool_call_id=f"call_card_{turn}",
            ),
        ]

    return _scripted(_parts)


def _built_state() -> PipelineState:
    state = lead_state()
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
    return state


async def _built_turn_ending_on_a_card(
    monkeypatch: pytest.MonkeyPatch,
    writer: Collector,
    replies: list[str],
) -> tuple[list[list[ModelMessage]], Any]:
    seen: list[list[ModelMessage]] = []
    monkeypatch.setattr(
        _lead_model, "get_mock_model", lambda: _card_turn(replies, seen)
    )
    state = _built_state()
    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    return seen, capture


def _card_beside_a_delete(reply: str, seen: list[list[ModelMessage]]) -> FunctionModel:
    """The first response writes the reply, a card and a delete; the next ends."""

    def _parts(messages: list[ModelMessage]) -> list[TextPart | ToolCallPart]:
        seen.append(messages)
        if len(seen) > 1:
            return [
                ToolCallPart(
                    tool_name="final_result", args=LEAD_FINAL, tool_call_id="call_end"
                )
            ]
        return [
            TextPart(content=reply),
            ToolCallPart(tool_name=PROPOSAL_TOOL, args=CARD_ARGS, tool_call_id=CARD),
            ToolCallPart(
                tool_name="delete_step", args={"step_id": "s1"}, tool_call_id=DELETE
            ),
        ]

    return _scripted(_parts)


def _calls_on_the_wire(writer: Collector) -> list[tuple[str, str]]:
    return [
        (p["chunk"]["type"], p["chunk"]["toolCallId"])
        for p in writer.payloads
        if "chunk" in p and "toolCallId" in p["chunk"]
    ]


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


class _WireChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    tool_call_id: str = Field(default="", alias="toolCallId")


def _wire(writer: Collector) -> list[str]:
    chunks = [
        _WireChunk.model_validate(p["chunk"]) for p in writer.payloads if "chunk" in p
    ]
    return [f"{c.type}:{c.tool_call_id}" for c in chunks]


def _asked(call_id: str) -> list[tuple[str, str]]:
    return [
        ("tool-input-start", call_id),
        ("tool-input-delta", call_id),
        ("tool-input-available", call_id),
        ("tool-approval-request", call_id),
    ]


def _returns_to(messages: list[ModelMessage], call_id: str) -> list[str]:
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_call_id == call_id
    ]


async def test_a_card_beside_another_approval_is_written_after_that_call(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[ModelMessage]] = []
    monkeypatch.setattr(
        _lead_model, "get_mock_model", lambda: _card_beside_a_delete(NAMES_IT, seen)
    )
    state = _built_state()

    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)

    assert len(seen) == 1
    assert _calls_on_the_wire(writer) == [*_asked(DELETE), *_asked(CARD)]
    wire = _wire(writer)
    delete_asked = wire.index(f"tool-approval-request:{DELETE}")
    assert (
        delete_asked
        < wire.index("text-start:")
        < wire.index(f"tool-input-start:{CARD}")
    )
    assert _written_text(writer) == NAMES_IT
    assert capture.pending_approval is not None
    assert capture.pending_approval.tool_call_id == CARD


async def test_a_denied_card_beside_another_approval_is_read_after_that_approval(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[ModelMessage]] = []
    monkeypatch.setattr(
        _lead_model,
        "get_mock_model",
        lambda: _card_beside_a_delete(LEAVES_IT_OUT, seen),
    )
    first = _built_state()
    parked = await drive_lead(state=first, deps=lead_deps(first), writer=writer)

    assert len(seen) == 1
    assert _calls_on_the_wire(writer) == _asked(DELETE)
    assert _written_text(writer) == ""
    assert parked.pending_approval is not None
    assert parked.pending_approval.tool_call_id == DELETE

    parked_run = len(writer.payloads)
    state = _built_state()
    state.user_message_id = first.user_message_id
    state.pending_approval = parked.pending_approval
    state.approval_responses = {
        DELETE: ToolApprovalResponded(id=DELETE, approved=False, reason="Keep it."),
    }
    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)

    assert len(seen) == 2
    correction = _returns_to(seen[1], CARD)
    assert len(correction) == 1
    assert "This reply does not match what the turn did:" in correction[0]
    assert SEARCH in correction[0]
    assert _returns_to(seen[1], DELETE) == ["Keep it."]
    resumed = [p["chunk"] for p in writer.payloads[parked_run:] if "chunk" in p]
    assert [(c["type"], c["toolCallId"]) for c in resumed[1:4]] == [
        ("tool-input-start", DELETE),
        ("tool-input-available", DELETE),
        ("tool-output-denied", DELETE),
    ]
    assert capture.pending_approval is None
