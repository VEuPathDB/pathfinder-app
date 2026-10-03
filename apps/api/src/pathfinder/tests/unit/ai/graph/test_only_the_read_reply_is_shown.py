"""A turn shows the reply the turn contract read and no other text of the Lead model."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    FinishStepChunk,
    StartStepChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
    ToolApprovalRequestChunk,
    ToolInputAvailableChunk,
    ToolInputDeltaChunk,
    ToolInputStartChunk,
)

from pathfinder.ai.graph._lead_capture import _emit_residual_prose, _LeadRunCapture
from pathfinder.ai.graph._lead_card_hold import CardHold
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.turn_facts import TurnFacts

_COMMENTARY = {
    "pydantic_ai": {
        "id": "msg_commentary",
        "provider_name": "openai",
        "provider_details": {"phase": "commentary"},
    }
}
_MESSAGE_ID = UUID("00000000-0000-0000-0000-000000000001")
_PROSE = "I can build this strategy, but one value is open."


class _Written(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    id: str = ""
    delta: str = ""


def _free_text(text_id: str, deltas: Sequence[str]) -> list[BaseChunk]:
    return [
        TextStartChunk(id=text_id, provider_metadata=_COMMENTARY),
        *(TextDeltaChunk(id=text_id, delta=delta) for delta in deltas),
        TextEndChunk(id=text_id, provider_metadata=_COMMENTARY),
    ]


def _final_result() -> list[BaseChunk]:
    call_id = "call_final"
    return [
        StartStepChunk(),
        ToolInputStartChunk(tool_call_id=call_id, tool_name="final_result"),
        ToolInputDeltaChunk(tool_call_id=call_id, input_text_delta='{"prose":"I'),
        ToolInputAvailableChunk(
            tool_call_id=call_id,
            tool_name="final_result",
            input={"prose": _PROSE, "strategyChanged": False},
        ),
        FinishStepChunk(),
    ]


def _through_hold(hold: CardHold, chunks: Sequence[BaseChunk]) -> list[BaseChunk]:
    written: list[BaseChunk] = []
    for chunk in chunks:
        written.extend(hold.admit(chunk))
    written.extend(hold.release(TurnFacts()))
    return written


def _types(chunks: Sequence[BaseChunk]) -> list[str]:
    return [
        _Written.model_validate(chunk.model_dump(by_alias=True)).type
        for chunk in chunks
    ]


def _texts(chunks: Sequence[BaseChunk]) -> list[_Written]:
    return [
        written
        for written in (
            _Written.model_validate(chunk.model_dump(by_alias=True)) for chunk in chunks
        )
        if written.type.startswith("text-")
    ]


def test_a_think_block_before_final_result_writes_no_text() -> None:
    think = _free_text("7cac3451", ["<th", "ink", ">\n\n", "</", "think", ">"])

    written = _through_hold(CardHold(), [*think, *_final_result()])

    assert _texts(written) == []
    assert _types(written) == [
        "start-step",
        "tool-input-start",
        "tool-input-delta",
        "tool-input-available",
        "finish-step",
    ]


def test_commentary_words_before_final_result_write_no_text() -> None:
    commentary = _free_text("c1", ["Let me check ", "the catalog."])

    assert _texts(_through_hold(CardHold(), [*commentary, *_final_result()])) == []


def test_the_reply_text_is_the_validated_output() -> None:
    think = _free_text("7cac3451", ["<think>\n\n</think>"])
    wire: list[dict[str, Any]] = [
        {"chunk": chunk.model_dump(by_alias=True, mode="json")}
        for chunk in _through_hold(CardHold(), [*think, *_final_result()])
    ]
    capture = _LeadRunCapture()
    capture.response = LeadResponse.model_validate(
        {"prose": _PROSE, "strategyChanged": False}
    )

    _emit_residual_prose(wire.append, capture, message_id=_MESSAGE_ID)

    texts = [
        _Written.model_validate(row["chunk"])
        for row in wire
        if row["chunk"]["type"].startswith("text-")
    ]
    assert texts == [
        _Written(type="text-start", id=f"lead-prose-{_MESSAGE_ID}"),
        _Written(type="text-delta", id=f"lead-prose-{_MESSAGE_ID}", delta=_PROSE),
        _Written(type="text-end", id=f"lead-prose-{_MESSAGE_ID}"),
    ]


def test_a_card_turn_writes_only_the_card_reply_before_the_card() -> None:
    call_id = "A"
    chunks = [
        *_free_text("c1", ["Let me check the catalog."]),
        ToolInputStartChunk(tool_call_id=call_id, tool_name=PROPOSAL_TOOL),
        ToolInputAvailableChunk(
            tool_call_id=call_id,
            tool_name=PROPOSAL_TOOL,
            input={"reply": "I can tighten both."},
        ),
        ToolApprovalRequestChunk(approval_id=call_id, tool_call_id=call_id),
        FinishStepChunk(),
    ]

    written = _through_hold(CardHold(), chunks)

    assert _texts(written) == [
        _Written(type="text-start", id="reply-A"),
        _Written(type="text-delta", id="reply-A", delta="I can tighten both."),
        _Written(type="text-end", id="reply-A"),
    ]
    assert _types(written) == [
        "finish-step",
        "text-start",
        "text-delta",
        "text-end",
        "tool-input-start",
        "tool-input-available",
        "tool-approval-request",
    ]
