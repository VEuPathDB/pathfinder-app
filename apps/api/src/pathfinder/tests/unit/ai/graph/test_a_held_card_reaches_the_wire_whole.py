"""Every card of a response is held whole and written after the reply it carries."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    FinishStepChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
    ToolApprovalRequestChunk,
    ToolInputAvailableChunk,
    ToolInputStartChunk,
    ToolOutputAvailableChunk,
    ToolOutputDeniedChunk,
)

from pathfinder.ai.graph._lead_card_hold import CardHold
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL


class _Label(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    tool_call_id: str = Field(default="", alias="toolCallId")

    def text(self) -> str:
        return f"{self.type}:{self.tool_call_id}"


def _labels(chunks: Sequence[BaseChunk]) -> list[str]:
    return [
        _Label.model_validate(chunk.model_dump(by_alias=True)).text()
        for chunk in chunks
    ]


def _written(hold: CardHold, chunks: Sequence[BaseChunk]) -> list[str]:
    written: list[BaseChunk] = []
    for chunk in chunks:
        written.extend(hold.admit(chunk))
    written.extend(hold.release())
    return _labels(written)


def _reply(text_id: str) -> list[BaseChunk]:
    return [
        TextStartChunk(id=text_id),
        TextDeltaChunk(id=text_id, delta="I can tighten both."),
        TextEndChunk(id=text_id),
    ]


def _started(call_id: str, tool_name: str) -> ToolInputStartChunk:
    return ToolInputStartChunk(tool_call_id=call_id, tool_name=tool_name)


def _available(call_id: str, tool_name: str) -> ToolInputAvailableChunk:
    return ToolInputAvailableChunk(
        tool_call_id=call_id,
        tool_name=tool_name,
        input={"reply": f"The reply card {call_id} carries."},
    )


def _asked(call_id: str) -> ToolApprovalRequestChunk:
    return ToolApprovalRequestChunk(approval_id=call_id, tool_call_id=call_id)


REPLY = ["text-start:", "text-delta:", "text-end:"]


def _card(call_id: str) -> list[str]:
    return [
        *REPLY,
        f"tool-input-start:{call_id}",
        f"tool-input-available:{call_id}",
        f"tool-approval-request:{call_id}",
    ]


def test_two_cards_of_one_response_are_written_each_after_its_reply() -> None:
    chunks = [
        *_reply("t"),
        _started("A", "consult_user"),
        _started("B", PROPOSAL_TOOL),
        _available("A", "consult_user"),
        _available("B", PROPOSAL_TOOL),
        _asked("A"),
        _asked("B"),
        FinishStepChunk(),
    ]

    assert _written(CardHold(), chunks) == [
        "finish-step:",
        *_card("A"),
        *_card("B"),
    ]


def test_a_denied_response_drops_its_reply_and_every_card() -> None:
    chunks = [
        *_reply("t0"),
        _started("A", "consult_user"),
        _started("B", PROPOSAL_TOOL),
        _available("A", "consult_user"),
        _available("B", PROPOSAL_TOOL),
        _asked("A"),
        _asked("B"),
        FinishStepChunk(),
        ToolOutputDeniedChunk(tool_call_id="A"),
        ToolOutputDeniedChunk(tool_call_id="B"),
        *_reply("t1"),
        _started("C", PROPOSAL_TOOL),
        _available("C", PROPOSAL_TOOL),
        _asked("C"),
        FinishStepChunk(),
    ]

    assert _written(CardHold(), chunks) == [
        "finish-step:",
        "finish-step:",
        *_card("C"),
    ]


def test_a_call_beside_a_card_is_written_at_once() -> None:
    hold = CardHold()
    for chunk in [*_reply("t"), _started("C", PROPOSAL_TOOL)]:
        assert hold.admit(chunk) == []

    beside = [
        _started("D", "verify_strategy"),
        _available("D", "verify_strategy"),
        _asked("D"),
    ]
    assert [_labels(hold.admit(chunk)) for chunk in beside] == [
        ["tool-input-start:D"],
        ["tool-input-available:D"],
        ["tool-approval-request:D"],
    ]
    assert _written(hold, [_available("C", PROPOSAL_TOOL), _asked("C")]) == [
        *_card("C"),
    ]


def test_a_resumed_run_writes_the_calls_it_re_announces_at_once() -> None:
    hold = CardHold(resumed={"A"})
    announced = [
        _started("A", PROPOSAL_TOOL),
        _available("A", PROPOSAL_TOOL),
        ToolOutputAvailableChunk(tool_call_id="A", output="Accepted."),
    ]

    assert [_labels(hold.admit(chunk)) for chunk in announced] == [
        ["tool-input-start:A"],
        ["tool-input-available:A"],
        ["tool-output-available:A"],
    ]
    assert _written(hold, [*_reply("t"), FinishStepChunk()]) == [
        *REPLY,
        "finish-step:",
    ]
