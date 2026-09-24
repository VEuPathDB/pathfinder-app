"""A turn that offers work parks on a proposal card, and the researcher's
answer decides what the resumed turn runs."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_stops import final_reply
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import lead_proposal
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL, DeclinedProposal
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff
from pathfinder.tests.unit.ai.graph._approval_turn import (
    LEAD_FINAL,
    Collector,
    drive_lead,
    holding_a_strategy,
    lead_deps,
    lead_state,
    scripted_model,
    tool_calls,
    writer,
)

__all__ = ["writer"]

CALL_ID = "call_propose_changes"
QUESTION = (
    "Refine the strategy to enforce strict 3-hour specificity and require 1:1:1 "
    "syntenic orthologs?"
)
CHANGES = [
    "Exclude genes highly expressed at the other post-blood-meal time points",
    "Require 1:1:1 syntenic orthologs in Aedes aegypti and Culex quinquefasciatus",
]
PROPOSAL_ARGS: dict[str, Any] = {"question": QUESTION, "proposedChanges": CHANGES}
NOTE = "Use the Liverpool strain for Aedes."
TWO_ADDED = EditDelta(
    diff=SpecDiff(
        changes=[
            CriterionChange(criterion_id="c_specific", disposition="added"),
            CriterionChange(criterion_id="c_syntenic", disposition="added"),
        ]
    ),
    description="Added two steps.",
    operations_applied=2,
    added_step_ids=["c_specific", "c_syntenic"],
)


def _proposing_lead(calls: list[list[ModelMessage]]) -> FunctionModel:
    """Offer the card first, then answer with the typed reply."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        calls.append(messages)
        if PROPOSAL_TOOL not in {c.tool_name for c in tool_calls(messages)}:
            return ToolCallPart(
                tool_name=PROPOSAL_TOOL, args=PROPOSAL_ARGS, tool_call_id=CALL_ID
            )
        return ToolCallPart(
            tool_name="final_result",
            args=LEAD_FINAL,
            tool_call_id=f"call_final_{uuid4().hex[:8]}",
        )

    return scripted_model(_part)


async def _parked_turn(
    monkeypatch: pytest.MonkeyPatch,
    writer: Collector,
    calls: list[list[ModelMessage]],
) -> tuple[PipelineState, PendingApproval]:
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: _proposing_lead(calls))
    state = lead_state()
    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    assert capture.pending_approval is not None
    return state, capture.pending_approval


def _resumed(first: PipelineState, pending: PendingApproval) -> PipelineState:
    state = lead_state()
    state.user_message_id = first.user_message_id
    state.pending_approval = pending
    return state


@pytest.fixture
def edits(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The edits a yes dispatches, each as the keyword arguments it ran with."""
    ran: list[dict[str, Any]] = []

    async def _run_edit(**kwargs: Any) -> EditDelta:
        ran.append(kwargs)
        return TWO_ADDED

    monkeypatch.setattr(lead_proposal, "run_edit", _run_edit)
    return ran


async def test_an_offer_parks_the_turn_on_a_card(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[ModelMessage]] = []
    _, pending = await _parked_turn(monkeypatch, writer, calls)

    assert pending.tool_name == PROPOSAL_TOOL
    assert pending.tool_args == PROPOSAL_ARGS
    requested = writer.chunks_of("tool-approval-request")
    assert [c["toolCallId"] for c in requested] == [CALL_ID]
    assert len(calls) == 1


async def test_no_ends_the_turn_without_a_model_call(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    edits: list[dict[str, Any]],
) -> None:
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    state = _resumed(first, pending)
    state.approval_responses = {
        CALL_ID: ToolApprovalResponded(id=CALL_ID, approved=False, reason="Not now."),
    }
    deps = lead_deps(state)

    capture = await drive_lead(state=state, deps=deps, writer=writer)

    assert len(calls) == 1
    assert edits == []
    assert capture.parked_call_answered is True
    assert capture.pending_approval is None
    assert final_reply(capture, None, changed=False) is None
    assert deps.state.domain.declined_proposal == DeclinedProposal(
        question=QUESTION, proposed_changes=CHANGES, note="Not now."
    )
    assert [c["toolCallId"] for c in writer.chunks_of("tool-output-denied")] == [
        CALL_ID
    ]
    summary = derive_ledger(deps.state, deps.intent).render_summary()
    assert "## Declined proposal" in summary
    assert CHANGES[1] in summary


async def test_a_resumed_run_writes_the_card_it_answers_as_it_arrives(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    edits: list[dict[str, Any]],
) -> None:
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    parked_run = len(writer.payloads)
    state = _resumed(first, pending)
    state.user_message_id = uuid4()
    state.user_prompt = "Show me the orthology step instead."

    await drive_lead(state=state, deps=lead_deps(state), writer=writer)

    resumed = [p["chunk"] for p in writer.payloads[parked_run:] if "chunk" in p]
    assert [c["type"] for c in resumed][:5] == [
        "data-turn-status",
        "tool-input-start",
        "tool-input-available",
        "tool-output-denied",
        "start-step",
    ]
    assert [c["toolCallId"] for c in resumed[1:4]] == [CALL_ID] * 3
    assert edits == []


async def test_yes_runs_the_cards_edit_and_the_lead_answers_once(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    edits: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(lead_proposal, "get_stream_writer", lambda: writer)
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    state = _resumed(first, pending)
    state.approval_responses = {
        CALL_ID: ToolApprovalResponded(id=CALL_ID, approved=True),
    }
    state.user_question_answers = {
        CALL_ID: [
            UserQuestionAnswer(
                question_id="proposal",
                prompt=QUESTION,
                chosen_labels=["Yes"],
                note=NOTE,
            )
        ],
    }
    deps = holding_a_strategy(lead_deps(state))

    capture = await drive_lead(state=state, deps=deps, writer=writer)

    assert len(calls) == 2
    assert [edit["parent_tool_call_id"] for edit in edits] == [CALL_ID]
    assert edits[0]["reason"] == (
        f"The researcher accepted this proposal: {QUESTION}\n"
        "Make these changes:\n"
        f"- {CHANGES[0]}\n"
        f"- {CHANGES[1]}\n"
        f"The researcher's note: {NOTE}"
    )
    assert capture.response is not None
    assert capture.response.prose == "scripted"
    assert deps.state.turn_markers.accepted_proposal is True
    outputs = writer.chunks_of("tool-output-available")
    assert CALL_ID in [c["toolCallId"] for c in outputs]
    cards = [
        c["data"]["state"]
        for c in writer.chunks_of("data-sub-agent-call")
        if c["data"]["toolCallId"] == CALL_ID
    ]
    assert cards == ["started", "completed"]


async def test_a_typed_yes_accepts_the_card(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    edits: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(lead_proposal, "get_stream_writer", lambda: writer)
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    state = _resumed(first, pending)
    state.user_message_id = uuid4()
    state.user_prompt = "Yes"
    deps = holding_a_strategy(lead_deps(state))

    capture = await drive_lead(state=state, deps=deps, writer=writer)

    assert [edit["reason"].splitlines()[-1] for edit in edits] == [f"- {CHANGES[1]}"]
    assert capture.response is not None


async def test_yes_on_a_thread_with_no_strategy_asks_the_lead_to_build(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    edits: list[dict[str, Any]],
) -> None:
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    state = _resumed(first, pending)
    state.approval_responses = {
        CALL_ID: ToolApprovalResponded(id=CALL_ID, approved=True),
    }

    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)

    assert edits == []
    retries = [
        str(part.content)
        for message in calls[-1]
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart) and part.tool_call_id == CALL_ID
    ]
    assert len(retries) == 1
    assert "frame_problem" in retries[0]
    assert CHANGES[0] in retries[0]
    assert capture.response is not None


async def test_a_typed_message_declines_the_card_and_reaches_the_lead(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    edits: list[dict[str, Any]],
) -> None:
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    state = _resumed(first, pending)
    state.user_message_id = uuid4()
    state.user_prompt = "Show me the orthology step instead."
    deps = lead_deps(state)

    capture = await drive_lead(state=state, deps=deps, writer=writer)

    assert edits == []
    assert len(calls) == 2
    assert capture.response is not None
    declined = deps.state.domain.declined_proposal
    assert declined is not None
    assert declined.proposed_changes == CHANGES
    assert [c["toolCallId"] for c in writer.chunks_of("tool-output-denied")] == [
        CALL_ID
    ]


async def test_an_unanswered_card_stays_parked(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    state = _resumed(first, pending)

    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)

    assert len(calls) == 1
    assert capture.pending_approval == pending
