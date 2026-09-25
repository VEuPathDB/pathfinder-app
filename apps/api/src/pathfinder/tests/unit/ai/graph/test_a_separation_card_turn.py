"""A separation result parks the turn on its adoption card, and the researcher's
answer decides what the resumed turn runs. A no keeps the offer."""

from __future__ import annotations

import dataclasses
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_stops import final_reply
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import lead_adoption
from pathfinder.ai.lead.deltas import ExecuteDelta
from pathfinder.ai.lead.proposal import ADOPT_TOOL, DeclinedProposal
from pathfinder.ai.lead.sub_agent_dispatch import MintedSpec
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.separation import AttachedControls
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.services.control_sets import ControlSetResponse, NewControlSet
from pathfinder.tests._support.database import detached_session
from pathfinder.tests._support.separation import TASK_ID, recorded_offer
from pathfinder.tests.unit.ai.graph._approval_turn import (
    CARD_REPLY,
    LEAD_FINAL,
    Collector,
    drive_lead,
    lead_deps,
    lead_state,
    scripted_model,
    tool_calls,
    writer,
)

__all__ = ["writer"]

CALL_ID = "call_adopt_separating_strategy"


def _adopting_lead(calls: list[list[ModelMessage]]) -> FunctionModel:
    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        calls.append(messages)
        if ADOPT_TOOL not in {c.tool_name for c in tool_calls(messages)}:
            return ToolCallPart(
                tool_name=ADOPT_TOOL,
                args={"task_id": str(TASK_ID), "reply": CARD_REPLY},
                tool_call_id=CALL_ID,
            )
        return ToolCallPart(
            tool_name="final_result",
            args=LEAD_FINAL,
            tool_call_id=f"call_final_{uuid4().hex[:8]}",
        )

    return scripted_model(_part)


def _offered_state() -> PipelineState:
    state = lead_state()
    state.domain.separation_offers = {str(TASK_ID): recorded_offer()}
    return state


async def _parked_turn(
    monkeypatch: pytest.MonkeyPatch,
    writer: Collector,
    calls: list[list[ModelMessage]],
) -> tuple[PipelineState, PendingApproval]:
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: _adopting_lead(calls))
    state = _offered_state()
    capture = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    assert capture.pending_approval is not None
    return state, capture.pending_approval


def _resumed(
    first: PipelineState, pending: PendingApproval, *, approved: bool
) -> PipelineState:
    state = _offered_state()
    state.user_message_id = first.user_message_id
    state.pending_approval = pending
    state.approval_responses = {
        CALL_ID: ToolApprovalResponded(id=CALL_ID, approved=approved),
    }
    return state


async def test_the_offer_parks_the_turn_on_its_card(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[ModelMessage]] = []
    _, pending = await _parked_turn(monkeypatch, writer, calls)

    assert (pending.tool_name, pending.tool_args) == (
        ADOPT_TOOL,
        {"task_id": str(TASK_ID), "reply": CARD_REPLY},
    )
    assert [c["delta"] for c in writer.chunks_of("text-delta")] == [CARD_REPLY]
    assert [c["toolCallId"] for c in writer.chunks_of("tool-approval-request")] == [
        CALL_ID
    ]


async def test_no_ends_the_turn_without_a_model_call_and_keeps_the_offer(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    state = _resumed(first, pending, approved=False)
    deps = lead_deps(state)

    capture = await drive_lead(state=state, deps=deps, writer=writer)

    offer = recorded_offer()
    assert len(calls) == 1
    assert final_reply(capture, None, changed=False) is None
    assert deps.state.domain.separation_offers == {str(TASK_ID): offer}
    assert deps.state.domain.declined_proposal == DeclinedProposal(
        question=offer.question,
        proposed_changes=[
            "GO Term: GO:0044217 other organism part (seed)",
            (
                "Gene Lists from PlasmoAP motif for protein export to the "
                "apicoplast. (seed)"
            ),
            (
                "GO Term: GO:0051701 biological process involved in interaction "
                "with host (seed)"
            ),
        ],
    )


async def test_yes_builds_the_offer_and_the_lead_answers_once(
    writer: Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[Any] = []

    async def _build(deps: LeadDeps, minted: MintedSpec) -> ExecuteDelta:
        del minted
        built.append(deps.state.domain.operational_spec)
        return ExecuteDelta(outcome=BuildOutcome(pushed_step_ids=["c4"]))

    async def _created(
        session: AsyncSession, spec: NewControlSet, *, user_id: UUID
    ) -> ControlSetResponse:
        del session
        return ControlSetResponse(
            id="control-set-1",
            name=spec.name,
            site_id=spec.site_id,
            record_type=spec.record_type,
            positive_ids=spec.positive_ids,
            negative_ids=spec.negative_ids,
            source=spec.source,
            tags=[],
            version=1,
            is_public=False,
            user_id=str(user_id),
            created_at="2026-09-24T00:00:00Z",
        )

    monkeypatch.setattr(lead_adoption, "build_the_minted", _build)
    monkeypatch.setattr(lead_adoption, "create_control_set", _created)
    calls: list[list[ModelMessage]] = []
    first, pending = await _parked_turn(monkeypatch, writer, calls)
    state = _resumed(first, pending, approved=True)
    deps = lead_deps(state)
    deps.runtime = dataclasses.replace(
        deps.runtime, db_session_factory=detached_session
    )

    await drive_lead(state=state, deps=deps, writer=writer)

    assert len(calls) == 2
    assert built == [recorded_offer().spec]
    offer = recorded_offer()
    assert deps.state.domain.attached_controls == AttachedControls(
        task_id=str(TASK_ID),
        control_set_id="control-set-1",
        positives=sorted([*offer.positive.returned, *offer.positive.not_returned]),
        negatives=sorted([*offer.negative.returned, *offer.negative.not_returned]),
    )
