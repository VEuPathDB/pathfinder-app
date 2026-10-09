from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_delta import _build_state_delta
from pathfinder.ai.graph._lead_stops import final_reply
from pathfinder.ai.lead import lead_proposal
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL, AddCriterionChange
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.tests.unit.ai.graph._approval_turn import (
    CARD_REPLY,
    Collector,
    drive_lead,
    lead_deps,
    lead_state,
    scripted_model,
    writer,
)

__all__ = ["writer"]

_CALL_ID = "call_propose_changes"
_PROPOSAL_ARGS: dict[str, Any] = {
    "question": "Add a time-point filter?",
    "proposedChanges": [
        AddCriterionChange(
            sentence="Exclude genes expressed at the other time points",
            search_name="GenesByRNASeqEvidence",
        ).model_dump(by_alias=True, mode="json")
    ],
    "reply": CARD_REPLY,
}
_NOTICE = (
    "The model declined this request. Its provider's biological safety filters "
    "blocked it. These filters sometimes block legitimate research questions "
    "(false positives). Try rephrasing it, or pick a different model in Settings."
)


def _proposing() -> FunctionModel:
    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        del messages
        return ToolCallPart(
            tool_name=PROPOSAL_TOOL, args=_PROPOSAL_ARGS, tool_call_id=_CALL_ID
        )

    return scripted_model(_part)


def _declining() -> FunctionModel:
    def _decline() -> ContentFilterError:
        return ContentFilterError("Content filter triggered. Finish reason: 'refusal'")

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        raise _decline()

    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del messages, info
        for _ in ():
            yield ""
        raise _decline()

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


@pytest.fixture(autouse=True)
def _edits(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run_edit(**_kwargs: Any) -> EditDelta:
        return EditDelta(diff=SpecDiff(changes=[]), description="Nothing changed.")

    monkeypatch.setattr(lead_proposal, "run_edit", _run_edit)


async def test_a_resumed_turn_the_model_declined_shows_the_notice_alone(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_lead_model, "get_mock_model", _proposing)
    first = lead_state()
    parked = await drive_lead(state=first, deps=lead_deps(first), writer=writer)
    assert parked.pending_approval is not None
    resumed = lead_state()
    resumed.user_message_id = first.user_message_id
    resumed.pending_approval = parked.pending_approval
    resumed.approval_responses = {
        _CALL_ID: ToolApprovalResponded(id=_CALL_ID, approved=True)
    }
    entry = resumed.model_copy(deep=True)
    deps = lead_deps(resumed)
    monkeypatch.setattr(_lead_model, "get_mock_model", _declining)
    declined = Collector()

    capture = await drive_lead(state=resumed, deps=deps, writer=declined)
    delta = _build_state_delta(state=entry, deps=deps, capture=capture, memories=[])

    assert declined.chunks_of("data-turn-withdrawn") == [
        {"type": "data-turn-withdrawn", "data": {"errorText": _NOTICE}}
    ]
    assert [chunk["errorText"] for chunk in declined.chunks_of("error")] == [_NOTICE]
    assert final_reply(capture, None, change="unchanged") is None
    assert delta["domain"] is entry.domain
    assert delta["pending_approval"] is None
