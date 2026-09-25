"""What the Lead's run reads when the researcher skips, types past or declines a card."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.approvals import DENIED_WITHOUT_REASON
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent_gate import DECLINED_OFFER_REFUSAL
from pathfinder.ai.lead.proposal import DeclinedProposal
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests.unit.ai.graph._approval_turn import (
    CARD_REPLY,
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

CALL_ID = "call_card"
TYPED = "Actually, keep the strategy and add a GO filter."
DECLINED_BY_REPLY = "The researcher sent a new message instead of answering the card."
CONSULT_ARGS: dict[str, Any] = {
    "questions": [{"id": "q1", "prompt": "Which strain?"}],
    "reply": CARD_REPLY,
}
CARDS = [
    ("clear_strategy", {"confirm": True, "reply": CARD_REPLY}),
    ("delete_step", {"step_id": "s1", "reply": CARD_REPLY}),
    ("consult_user", CONSULT_ARGS),
]


def _carding_lead(
    tool_name: str, args: dict[str, Any], calls: list[list[ModelMessage]]
) -> FunctionModel:
    """Raise the card first, then answer."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        calls.append(messages)
        if tool_name not in {c.tool_name for c in tool_calls(messages)}:
            return ToolCallPart(tool_name=tool_name, args=args, tool_call_id=CALL_ID)
        return ToolCallPart(
            tool_name="final_result",
            args=LEAD_FINAL,
            tool_call_id=f"call_final_{uuid4().hex[:8]}",
        )

    return scripted_model(_part)


async def _answered(
    monkeypatch: pytest.MonkeyPatch,
    writer: Collector,
    card: tuple[str, dict[str, Any]],
    answer: Any,
) -> tuple[LeadDeps, _LeadRunCapture, list[list[ModelMessage]]]:
    """Park the turn on ``card``, then run the turn ``answer`` shapes."""
    calls: list[list[ModelMessage]] = []
    monkeypatch.setattr(
        _lead_model, "get_mock_model", lambda: _carding_lead(*card, calls)
    )
    first = lead_state()
    parked = await drive_lead(
        state=first, deps=holding_a_strategy(lead_deps(first)), writer=writer
    )
    assert parked.pending_approval is not None
    state = lead_state()
    state.user_message_id = first.user_message_id
    state.pending_approval = parked.pending_approval
    answer(state)
    deps = holding_a_strategy(lead_deps(state))
    capture = await drive_lead(state=state, deps=deps, writer=writer)
    return deps, capture, calls


def _typed(state: PipelineState) -> None:
    state.user_message_id = uuid4()
    state.user_prompt = TYPED


def _skipped(state: PipelineState) -> None:
    state.approval_responses = {
        CALL_ID: ToolApprovalResponded(id=CALL_ID, approved=False),
    }


def _resumed_reads(calls: list[list[ModelMessage]]) -> tuple[list[Any], list[Any]]:
    """The card's return and the prompts the resumed run's model call read."""
    requests = [m for m in calls[-1] if isinstance(m, ModelRequest)]
    returns = [
        part.content
        for m in requests
        for part in m.parts
        if isinstance(part, ToolReturnPart) and part.tool_call_id == CALL_ID
    ]
    prompts = [
        part.content
        for m in requests
        for part in m.parts
        if isinstance(part, UserPromptPart)
    ]
    return returns, prompts


@pytest.mark.parametrize("card", CARDS, ids=[name for name, _ in CARDS])
async def test_a_typed_message_declines_the_card_and_reaches_the_lead(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    card: tuple[str, dict[str, Any]],
) -> None:
    deps, capture, calls = await _answered(monkeypatch, writer, card, _typed)

    returns, prompts = _resumed_reads(calls)
    assert len(calls) == 2
    assert returns == [DECLINED_BY_REPLY]
    assert TYPED in prompts
    assert capture.pending_approval is None
    assert capture.response is not None
    assert deps.runtime.strategy_session.get_graph(None) is not None
    assert deps.state.domain.declined_proposal is None
    denied = [c["toolCallId"] for c in writer.chunks_of("tool-output-denied")]
    assert denied == [CALL_ID]


async def test_a_skipped_question_card_reaches_the_lead_as_declined(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps, capture, calls = await _answered(
        monkeypatch, writer, ("consult_user", CONSULT_ARGS), _skipped
    )

    returns, _ = _resumed_reads(calls)
    assert len(calls) == 2
    assert returns == [DENIED_WITHOUT_REASON]
    assert deps.state.domain.requirements == []
    assert deps.state.turn_markers.consulted is False
    assert capture.response is not None
    denied = [c["toolCallId"] for c in writer.chunks_of("tool-output-denied")]
    assert denied == [CALL_ID]


async def test_a_bare_yes_after_a_declined_offer_ends_on_the_refusal(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[ModelMessage]] = []
    monkeypatch.setattr(
        _lead_model,
        "get_mock_model",
        lambda: _carding_lead("frame_problem", {"reason": "build it"}, calls),
    )
    state = lead_state()
    state.user_prompt = "yes, do it"
    state.domain.declined_proposal = DeclinedProposal(
        question="Refine the strategy to require 1:1:1 syntenic orthologs?",
        proposed_changes=["Require 1:1:1 syntenic orthologs in Aedes aegypti"],
    )

    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)

    assert calls == []
    assert capture.response is not None
    assert capture.response.prose == DECLINED_OFFER_REFUSAL
    assert capture.response.strategy_changed is False
