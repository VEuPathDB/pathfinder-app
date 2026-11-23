from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import (
    DurableDeferral,
    SubAgentApprovalCall,
    SubAgentApprovalPending,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from veupathdb.domain.strategy import StrategyStepNode

from strategist.ai.graph import _lead_model
from strategist.ai.graph._lead_capture import LeadRunCapture
from strategist.ai.graph.lead_node import _drive_lead_stream
from strategist.ai.graph.state import VerificationDigest
from strategist.ai.lead import (
    evidence_card,
    sub_agent_dispatch,
    sub_agent_stream,
    verify_dispatch,
)
from strategist.ai.lead.deltas import VerificationDelta, VerificationStopped
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from strategist.ai.lead.sub_agent_stream import SubAgentApprovalWait
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.domain.strategy.session import StrategySession
from strategist.services.strategies.context import StrategyMutationContext
from strategist.tests._support.scripted import scripted_with
from strategist.tests._support.scripted_reading import read_as
from strategist.tests._support.site_checks import checked_site
from strategist.tests.unit.ai.graph._approval_turn import Collector, scripted_model
from strategist.tests.unit.ai.graph.test_lead_turn_budget import _deps, _framed_state
from strategist.tests.unit.ai.lead._budget_stop_turn import (
    SITE_ID,
    built_outcome,
    hold_the_built_step,
)
from strategist.tests.unit.ai.lead.conftest import (
    called_tool_names,
    final_result_part,
)

_FIRST = "I added the step to the strategy."
_CHECKED = "I added the step, and the check of it passed."
_READ = "The sampled records are upregulated genes."
_BUDGET = PhaseStop(role="verification", reason=PhaseStopReason.BUDGET, tool_calls=40)


async def _push(
    *,
    deps: StrategyMutationContext,
    root: StrategyStepNode,
    description: str | None = None,
) -> BuildOutcome:
    del description
    hold_the_built_step(deps.strategy_session, root.id)
    return built_outcome(root.id)


async def _no_gene_set(**_kwargs: object) -> None:
    return None


def _returns(messages: list[ModelMessage], tool: str) -> list[object]:
    return [
        part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == tool
    ]


class _Lead:
    def __init__(self, *, verifies: bool = False, asks: bool = False) -> None:
        self.verifies = verifies
        self.asks = asks
        self.calls = 0
        self.seen: list[list[ModelMessage]] = []

    def __call__(self, messages: list[ModelMessage]) -> ToolCallPart:
        self.calls += 1
        self.seen.append(list(messages))
        called = called_tool_names(messages)
        if "build_strategy" not in called:
            return ToolCallPart(
                tool_name="build_strategy", args={}, tool_call_id="call_build"
            )
        if self.asks:
            return ToolCallPart(
                tool_name="consult_user",
                args={
                    "questions": [
                        {
                            "id": "q1",
                            "prompt": "Keep the step?",
                            "kind": "single_choice",
                            "options": [{"label": "Keep"}, {"label": "Drop"}],
                        }
                    ],
                    "reply": _FIRST,
                },
                tool_call_id="call_card",
            )
        if self.verifies and "verify_strategy" not in called:
            return ToolCallPart(
                tool_name="verify_strategy",
                args={"reason": "check the built step"},
                tool_call_id="call_verify",
            )
        prose = _CHECKED if "verify_strategy" in called else _FIRST
        return final_result_part({"prose": prose, "nextState": "await_user"})


def _turn(
    monkeypatch: pytest.MonkeyPatch, lead: _Lead, verifier: Any
) -> tuple[LeadDeps, LeadRunCapture]:
    model = scripted_model(lead)
    read_as(monkeypatch, "extend_strategy")
    monkeypatch.setattr(_lead_model, "scripted", scripted_with(model=lambda: model))
    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _push)
    monkeypatch.setattr(
        sub_agent_dispatch, "import_gene_set_for_conversation", _no_gene_set
    )
    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", verifier)
    checked_site(monkeypatch)
    writer = Collector()
    for module in (sub_agent_dispatch, sub_agent_stream, evidence_card):
        monkeypatch.setattr(module, "get_stream_writer", lambda: writer)
    state = _framed_state()
    deps = _deps(state, StrategySession(site_id=SITE_ID))
    capture = LeadRunCapture()
    emitted: Any = writer
    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=deps,
            capture=capture,
            writer=emitted,
            message_id=uuid4(),
        ),
    )
    return deps, capture


async def _reviewed(**_kwargs: object) -> VerificationDelta:
    return VerificationDelta(digest=VerificationDigest(prose=_READ))


def test_a_build_answered_with_no_check_is_checked_then_answered_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = _Lead()

    deps, capture = _turn(monkeypatch, lead, _reviewed)

    assert capture.response is not None
    markers = deps.state.turn_markers
    verdict = deps.state.turn_verdict
    assert (
        capture.response.prose,
        lead.calls,
        markers.answer_ledger.uses,
        verdict is not None and verdict.success,
    ) == (_CHECKED, 3, (), True)
    [checked] = _returns(lead.seen[-1], "verify_strategy")
    assert VerificationDelta.model_validate(checked).digest.prose == _READ


def test_a_lead_that_checked_is_not_checked_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = _Lead(verifies=True)
    ran: list[object] = []

    async def _counted(**kwargs: object) -> VerificationDelta:
        ran.append(kwargs)
        return await _reviewed()

    _, capture = _turn(monkeypatch, lead, _counted)

    assert capture.response is not None
    assert (capture.response.prose, lead.calls, len(ran)) == (_CHECKED, 3, 1)


def test_a_turn_that_ends_on_a_card_is_not_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = _Lead(asks=True)
    ran: list[object] = []

    async def _counted(**kwargs: object) -> VerificationDelta:
        ran.append(kwargs)
        return await _reviewed()

    _, capture = _turn(monkeypatch, lead, _counted)

    assert (capture.pending_approval is not None, lead.calls, ran) == (True, 2, [])


def test_a_check_that_stops_on_its_budget_resumes_the_lead_with_the_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = _Lead()

    async def _stopped(*, deps: LeadDeps, **_kwargs: object) -> None:
        deps.last_phase_stop = _BUDGET

    deps, capture = _turn(monkeypatch, lead, _stopped)

    assert capture.response is not None
    [stopped] = _returns(lead.seen[-1], "verify_strategy")
    assert (capture.response.prose, lead.calls) == (_CHECKED, 3)
    assert VerificationStopped.model_validate(stopped).stop == _BUDGET
    assert deps.state.turn_markers.build_unverified is True
    assert turn_facts(deps).stopped_check == _BUDGET.render()


_PARKED = SubAgentApprovalWait(
    pending=SubAgentApprovalPending(
        role="verification",
        approvals=[
            SubAgentApprovalCall(
                tool_call_id="call_controls", tool_name="run_control_tests_on_step"
            )
        ],
        messages_json=ModelMessagesTypeAdapter.dump_json(
            [ModelRequest(parts=[UserPromptPart(content="check the strategy")])]
        ).decode(),
    ),
    durable={
        "call_controls": DurableDeferral(
            task_id=uuid4(), tool_name="run_control_tests_on_step"
        )
    },
)


def test_a_check_that_defers_parks_the_turn_on_the_runtimes_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = _Lead()

    async def _parks(**_kwargs: object) -> SubAgentApprovalWait:
        return _PARKED

    _, capture = _turn(monkeypatch, lead, _parks)

    parked = capture.pending_durable_call
    assert parked is not None
    assert (capture.response, lead.calls, parked.tool_name) == (
        None,
        2,
        "verify_strategy",
    )
    assert parked.tool_call_id.startswith("call_runtime_check_")
