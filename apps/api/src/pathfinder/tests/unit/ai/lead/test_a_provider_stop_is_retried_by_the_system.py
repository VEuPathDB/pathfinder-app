"""A model request the provider did not complete stops the pass as typed data,
and the system sends the pass once more; a refusal of the request is raised."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.lead import frame_dispatch, sub_agent_stream, verify_dispatch
from pathfinder.ai.lead.deltas import FrameResult, VerificationDelta
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import PhaseRun, stream_sub_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.lead.test_a_stopped_check_is_no_check import (
    _EARLIER,
    _checked_earlier,
)

pytestmark = pytest.mark.usefixtures("collector")

_PROVIDER_STOP = PhaseStop(role="frame", reason=PhaseStopReason.PROVIDER)


def _failing_model(error: Exception) -> FunctionModel:
    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        raise error

    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        del messages, info
        raise error
        yield ""

    return FunctionModel(_fn, stream_function=_stream, model_name="failing")


@pytest.fixture
def frame_on(monkeypatch: pytest.MonkeyPatch) -> Callable[[Exception], Any]:
    monkeypatch.setattr(
        sub_agent_stream, "phase_override_kwargs", lambda runtime, role: {}
    )

    def _pin(error: Exception) -> Any:
        return pinned_sub_agent(
            monkeypatch,
            "frame",
            model=_failing_model(error),
            toolsets=[],
            instructions="Frame.",
        )

    return _pin


async def _frame_pass(deps: LeadDeps) -> FrameResult | None:
    result = await stream_sub_agent(
        run=PhaseRun("frame", "frame it"),
        agent_deps=agent_deps_for(deps),
        parent_tool_call_id="t1",
        expected_output_type=FrameResult,
        deps=deps,
    )
    assert not isinstance(result, sub_agent_stream.SubAgentApprovalWait)
    return result


async def test_a_request_the_provider_did_not_complete_is_a_typed_stop(
    frame_on: Any,
) -> None:
    deps = lead_deps(pipeline_state(user_prompt="Find the kinases."))

    with frame_on(ModelAPIError("gpt-x", "The provider did not complete the request.")):
        result = await _frame_pass(deps)

    assert (result, deps.last_phase_stop) == (
        None,
        PhaseStop(role="frame", reason=PhaseStopReason.PROVIDER),
    )


async def test_a_server_error_is_the_same_stop(frame_on: Any) -> None:
    deps = lead_deps(pipeline_state(user_prompt="Find the kinases."))

    with frame_on(ModelHTTPError(status_code=503, model_name="gpt-x")):
        result = await _frame_pass(deps)

    assert (result, deps.last_phase_stop) == (None, _PROVIDER_STOP)


async def test_a_refused_request_is_raised_not_stopped(frame_on: Any) -> None:
    deps = lead_deps(pipeline_state(user_prompt="Find the kinases."))

    with (
        frame_on(ModelHTTPError(status_code=400, model_name="gpt-x")),
        pytest.raises(ModelHTTPError),
    ):
        await _frame_pass(deps)

    assert deps.last_phase_stop is None


def test_the_stop_names_the_provider() -> None:
    assert _PROVIDER_STOP.render() == (
        "the framing pass stopped on a model request the provider did not "
        "complete after 0 calls"
    )


async def test_the_frame_is_sent_once_more_whatever_it_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str | None] = []

    async def _streamed(**kwargs: Any) -> FrameResult | None:
        deps: LeadDeps = kwargs["deps"]
        calls.append(kwargs["run"].work_order[:12])
        if len(calls) == 1:
            deps.last_phase_stop = _PROVIDER_STOP
            return None
        kwargs["agent_deps"].agent_state.operational_spec_draft.criteria.append(
            Criterion(id="c1", text="kinases", search_name="GenesByText")
        )
        return FrameResult(disposition="spec_ready", summary="framed")

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _streamed)
    deps = lead_deps(pipeline_state(user_prompt="Find the kinases."))

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps),
    )

    assert isinstance(result, FrameResult)
    assert (len(calls), deps.frame_retried_after_stop) == (2, True)


async def test_a_second_provider_stop_reaches_the_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def _streamed(**kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        kwargs["deps"].last_phase_stop = _PROVIDER_STOP

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _streamed)
    deps = lead_deps(pipeline_state(user_prompt="Find the kinases."))

    await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("f", deps)
    )

    assert (calls, deps.last_phase_stop) == (2, _PROVIDER_STOP)


async def test_the_check_is_sent_once_more_after_a_provider_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def _streamed(
        *, deps: LeadDeps, **_kwargs: object
    ) -> VerificationDelta | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            deps.last_phase_stop = _PROVIDER_STOP.model_copy(
                update={"role": "verification"}
            )
            return None
        deps.last_phase_stop = None
        return VerificationDelta(digest=_EARLIER)

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", _streamed)
    state, session = _checked_earlier()
    deps = lead_deps(state, strategy_session=session)

    result = await run_verification(
        deps=deps, parent_tool_call_id="call_verify", reason="check the strategy"
    )

    assert isinstance(result, VerificationDelta)
    assert (calls, deps.verify_retried_after_stop) == (2, True)
