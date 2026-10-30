from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import DurableDeferral, SubAgentApprovalPending
from pydantic_ai.exceptions import CallDeferred, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import DeferredToolResults

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.lead import sub_agent_tools, verify_dispatch
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.ai.lead.deltas import VerificationDelta, VerificationStopped
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, hold_the_turn_contract
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.lead.verify_dispatch import run_verification, verify_strategy
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.turn_facts import UNVERIFIED_BUILD
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    built_outcome,
    built_session,
    objection,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    final_result_model,
    lead_deps,
    pipeline_state,
)

_WHY = "the verification pass stopped before it finished"
_REPLY = f"I added the step. It is not checked yet, because {_WHY}."


def _built_this_turn() -> LeadDeps:
    session = built_session()
    state = pipeline_state(user_prompt="find the 24 h responders")
    state.user_message_id = uuid4()
    state.record_build(built_outcome())
    state.domain.answered_graph = live_tree(session.get_graph(None))
    return lead_deps(state, strategy_session=session)


_SPENT = "The next request would exceed the request_limit of 40"


def _over_budget(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del messages, info
    raise UsageLimitExceeded(_SPENT)


async def _over_budget_streamed(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str]:
    del messages, info
    raise UsageLimitExceeded(_SPENT)
    yield ""


def _misshapen() -> Any:
    return final_result_model({"digest": {"keyFindings": "Checked."}})


def _over_budget_model() -> Any:
    return FunctionModel(
        _over_budget, stream_function=_over_budget_streamed, model_name="scripted"
    )


async def _verify_on(
    monkeypatch: pytest.MonkeyPatch, deps: LeadDeps, model: Any
) -> VerificationDelta | VerificationStopped | object:
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", lambda: model)
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Follow the script.",
    ):
        return await run_verification(
            deps=deps, parent_tool_call_id="call_verify", reason="check the strategy"
        )


def _unverified(deps: LeadDeps) -> str:
    return turn_record(replace(run_context_for(deps), retries={})).facts.unverified


@pytest.mark.parametrize(
    ("model", "reason"),
    [
        (_over_budget_model, PhaseStopReason.BUDGET),
        (_misshapen, PhaseStopReason.OUTPUT_RETRIES),
    ],
)
async def test_a_stopped_check_leaves_the_status_and_takes_a_reason(
    monkeypatch: pytest.MonkeyPatch,
    collector: ChunkCollector,
    model: Any,
    reason: PhaseStopReason,
) -> None:
    del collector
    deps = _built_this_turn()

    result = await _verify_on(monkeypatch, deps, model())
    answer = LeadResponse(prose=_REPLY, unverified_reason=_WHY)

    assert isinstance(result, VerificationStopped)
    assert result.stop == PhaseStop(role="verification", reason=reason)
    assert result.summary.endswith(
        "Set `unverifiedReason` to why the check did not finish."
    )
    assert _unverified(deps) == UNVERIFIED_BUILD
    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    markers = deps.state.turn_markers
    assert (markers.output_refusals, markers.unchecked_reply) == (0, False)


@pytest.mark.parametrize(
    "digest", [objection(), objection().model_copy(update={"success": True})]
)
async def test_a_check_that_returns_its_review_clears_the_status(
    monkeypatch: pytest.MonkeyPatch,
    collector: ChunkCollector,
    digest: VerificationDigest,
) -> None:
    del collector
    deps = _built_this_turn()
    await _verify_on(monkeypatch, deps, _misshapen())

    async def reviewed(**_kwargs: object) -> VerificationDelta:
        return VerificationDelta(digest=digest)

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", reviewed)
    result = await run_verification(
        deps=deps, parent_tool_call_id="call_verify_2", reason="check it again"
    )

    assert isinstance(result, VerificationDelta)
    assert _unverified(deps) == ""


_PARKED = SubAgentApprovalWait(
    pending=SubAgentApprovalPending(role="verification"),
    durable={
        "call_controls": DurableDeferral(
            task_id=uuid4(), tool_name="run_control_tests_on_step"
        )
    },
)


async def _parked_check(monkeypatch: pytest.MonkeyPatch) -> LeadDeps:
    async def parks(**_kwargs: object) -> SubAgentApprovalWait:
        return _PARKED

    deps = _built_this_turn()
    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", parks)
    with pytest.raises(CallDeferred):
        await verify_strategy(
            run_context_for(deps, "call_verify"), reason="check the strategy"
        )
    return deps


async def _resumed(
    monkeypatch: pytest.MonkeyPatch,
    parked: LeadDeps,
    outcome: VerificationDelta | None,
) -> LeadDeps:
    async def answers(*, deps: LeadDeps, **_kwargs: object) -> VerificationDelta | None:
        deps.last_phase_stop = (
            PhaseStop(role="verification", reason=PhaseStopReason.BUDGET)
            if outcome is None
            else None
        )
        return outcome

    deps = lead_deps(parked.state, strategy_session=parked.runtime.strategy_session)
    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", answers)
    await run_verification(
        deps=deps,
        parent_tool_call_id="call_verify",
        reason="check the strategy",
        resume=SubAgentResume(
            messages=[], results=DeferredToolResults(), on_the_card=frozenset()
        ),
    )
    return deps


async def test_a_check_parked_on_its_task_shows_no_status(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    del collector
    deps = await _parked_check(monkeypatch)

    markers = deps.state.turn_markers
    assert (markers.verification_stopped, markers.build_unverified) == (True, True)
    assert _unverified(deps) == ""


async def test_a_parked_check_that_returns_its_review_shows_no_status(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    del collector
    parked = await _parked_check(monkeypatch)

    deps = await _resumed(monkeypatch, parked, VerificationDelta(digest=objection()))

    assert _unverified(deps) == ""


async def test_a_parked_check_that_stops_on_resume_shows_the_status(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    del collector
    parked = await _parked_check(monkeypatch)

    deps = await _resumed(monkeypatch, parked, None)

    assert _unverified(deps) == UNVERIFIED_BUILD
