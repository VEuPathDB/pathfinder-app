"""A dispatch that stops early records the stop and its usage on the Lead's deps."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from pydantic_ai import RunContext, Tool
from pydantic_ai.exceptions import ModelRetry, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import sub_agent_stream
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import PhaseRun, stream_sub_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, SubAgentRunUsage
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    called_tool_names,
    endless_tool_call_model,
    final_result_model,
    lead_deps,
    pipeline_state,
    tool_script_model,
)

pytestmark = pytest.mark.usefixtures("collector")


def _deps(usage_log: list[SubAgentRunUsage] | None = None) -> LeadDeps:
    return lead_deps(
        pipeline_state(user_prompt="Find the kinases."),
        record_usage=None if usage_log is None else usage_log.append,
    )


@pytest.fixture(autouse=True)
def _no_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sub_agent_stream,
        "phase_override_kwargs",
        lambda runtime, role: {},
    )


async def bind_one(ctx: RunContext[AgentDeps]) -> str:
    """Bind one more criterion into the shared draft, as FRAME's tools do."""
    draft = ctx.deps.agent_state.operational_spec_draft
    index = len(draft.criteria)
    draft.criteria.append(
        Criterion(
            id=f"c{index}",
            text=f"criterion {index}",
            search_name="GenesByText",
        ),
    )
    return "bound"


async def ping(ctx: RunContext[AgentDeps]) -> str:
    del ctx
    return "pong"


REFUSAL = "STRUCTURE_REFUSED: the combine names a criterion the spec omits."


async def refuse_always(ctx: RunContext[AgentDeps]) -> str:
    """Refuse every call, as a structure check refuses a bad combine."""
    del ctx
    raise ModelRetry(REFUSAL)


async def needs_int(ctx: RunContext[AgentDeps], count: int) -> str:
    """Take an argument the scripted model never sends in the right type."""
    del ctx
    return str(count)


_OTHER_CRASH = "Model token limit (4096) exceeded before any response was generated."


def _crash_after_one_refusal(messages: list[ModelMessage]) -> ToolCallPart:
    """Call the refusing tool once, then fail for an unrelated reason."""
    if "refuse_always" in called_tool_names(messages):
        raise UnexpectedModelBehavior(_OTHER_CRASH)
    return ToolCallPart(
        tool_name="refuse_always", args="{}", tool_call_id="call_refuse_1"
    )


def _pinned(
    monkeypatch: pytest.MonkeyPatch, model: FunctionModel, tool: Any
) -> Iterator[None]:
    toolset = FunctionToolset[AgentDeps](tools=[Tool(tool)])
    with pinned_sub_agent(
        monkeypatch,
        "frame",
        model=model,
        toolsets=[toolset],
        instructions="Call the tool.",
    ):
        yield


@pytest.fixture
def binding_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield from _pinned(monkeypatch, endless_tool_call_model("bind_one"), bind_one)


@pytest.fixture
def looping_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield from _pinned(monkeypatch, endless_tool_call_model("ping"), ping)


@pytest.fixture
def refusing_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield from _pinned(
        monkeypatch, endless_tool_call_model("refuse_always"), refuse_always
    )


@pytest.fixture
def crashing_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield from _pinned(
        monkeypatch, tool_script_model(_crash_after_one_refusal), refuse_always
    )


@pytest.fixture
def mistyped_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    model = tool_script_model(
        lambda _messages: ToolCallPart(
            tool_name="needs_int",
            args={"count": "not a number"},
            tool_call_id="call_needs_int",
        ),
    )
    yield from _pinned(monkeypatch, model, needs_int)


@pytest.fixture
def answering_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    model = final_result_model(
        {"summary": "one criterion bound", "disposition": "needs_user"},
    )
    yield from _pinned(monkeypatch, model, ping)


def _cap_tool_calls(monkeypatch: pytest.MonkeyPatch, limit: int) -> None:
    monkeypatch.setattr(
        sub_agent_stream,
        "phase_usage_limits",
        lambda declared_criteria: UsageLimits(
            request_limit=10,
            tool_calls_limit=limit,
            total_tokens_limit=2_000_000,
        ),
    )


def _stop_reason(deps: LeadDeps) -> str:
    """The reason the last pass stopped, empty when it ran to an answer."""
    stop = deps.last_phase_stop
    return "" if stop is None else stop.reason.value


async def _dispatch(
    deps: LeadDeps,
    declared: int = 8,
    guard: ToolRepetitionGuard | None = None,
) -> object:
    agent_deps = agent_deps_for(deps)
    if guard is not None:
        agent_deps.tool_repetition_guard = guard
    return await stream_sub_agent(
        run=PhaseRun(
            "frame", frame_work_order("bind the criteria", deps.state), declared
        ),
        agent_deps=agent_deps,
        parent_tool_call_id="call_frame_1",
        expected_output_type=FrameResult,
        deps=deps,
    )


@pytest.mark.usefixtures("binding_frame")
async def test_a_budget_stop_is_recorded_with_its_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cap_tool_calls(monkeypatch, 3)
    deps = _deps()

    delta = await _dispatch(deps)

    assert delta is None
    stop = deps.last_phase_stop
    assert stop is not None
    assert stop.reason is PhaseStopReason.BUDGET
    assert stop.role == "frame"
    assert stop.tool_calls == 3
    assert stop.criteria_bound == 3
    assert stop.criteria_declared == 8


@pytest.mark.usefixtures("looping_frame")
async def test_a_repetition_stop_names_the_repeated_call() -> None:
    guard = ToolRepetitionGuard(read_only_tools=frozenset({"ping"}), threshold=2)
    deps = _deps()

    delta = await _dispatch(deps, guard=guard)

    assert delta is None
    stop = deps.last_phase_stop
    assert stop is not None
    assert stop.reason is PhaseStopReason.REPEATED_CALL
    assert stop.role == "frame"


@pytest.mark.usefixtures("answering_frame")
async def test_a_clean_dispatch_records_no_stop() -> None:
    deps = _deps()

    delta = await _dispatch(deps)

    assert isinstance(delta, FrameResult)
    assert delta.disposition == "needs_user"
    assert _stop_reason(deps) == ""


@pytest.mark.usefixtures("answering_frame")
async def test_an_earlier_stop_does_not_reach_a_later_clean_pass() -> None:
    deps = _deps()
    deps.last_phase_stop = PhaseStop(
        role="frame",
        reason=PhaseStopReason.BUDGET,
        tool_calls=60,
        criteria_bound=3,
        criteria_declared=8,
    )

    await _dispatch(deps)

    assert _stop_reason(deps) == ""


@pytest.mark.usefixtures("looping_frame")
async def test_budget_stopped_dispatch_records_its_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cap_tool_calls(monkeypatch, 1)
    usage_log: list[SubAgentRunUsage] = []
    deps = _deps(usage_log)

    await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("operationalize the goal", deps.state),
    )

    assert usage_log, "a budget-stopped dispatch must record its usage"
    recorded = usage_log[-1]
    assert recorded.parent_tool_call_id == "call_frame_1"
    assert recorded.usage.total_tokens > 0


@pytest.mark.usefixtures("refusing_frame")
async def test_a_tool_refused_past_its_retries_is_a_stop() -> None:
    """An exhausted tool retry stops the pass; it does not crash the turn."""
    deps = _deps()

    delta = await _dispatch(deps)

    assert delta is None
    stop = deps.last_phase_stop
    assert stop is not None
    assert stop.reason is PhaseStopReason.TOOL_RETRIES
    assert stop.role == "frame"
    assert stop.tool_name == "refuse_always"
    rendered = stop.render()
    assert REFUSAL in rendered
    assert "pydantic" not in rendered


@pytest.mark.usefixtures("refusing_frame")
async def test_a_refused_pass_hands_the_lead_the_refusals_words() -> None:
    """The dispatch answers, and the ledger the Lead reads quotes the refusal."""
    deps = _deps()

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("bind the criteria", deps.state),
    )

    assert isinstance(result, FrameResult)
    assert result.disposition == "needs_user"
    stop = deps.last_phase_stop
    assert stop is not None
    assert (stop.tool_name, stop.refusal) == ("refuse_always", REFUSAL)
    ledger = derive_ledger(deps.state, deps.intent, phase_stop=stop)
    assert f"- stopped: {stop.render()}" in ledger.render_summary()


@pytest.mark.usefixtures("crashing_frame")
async def test_a_model_failure_of_another_kind_still_ends_the_run() -> None:
    """Only an exhausted tool retry is a stop; every other crash propagates."""
    deps = _deps()

    with pytest.raises(UnexpectedModelBehavior) as raised:
        await _dispatch(deps)

    assert str(raised.value) == _OTHER_CRASH
    assert deps.last_phase_stop is None


@pytest.mark.usefixtures("mistyped_frame")
async def test_a_validation_refusal_reaches_the_ledger_without_its_json() -> None:
    """The stop quotes what the validator said, not the library's error dump."""
    deps = _deps()

    delta = await _dispatch(deps)

    assert delta is None
    stop = deps.last_phase_stop
    assert stop is not None
    assert (stop.reason, stop.tool_name) == (
        PhaseStopReason.TOOL_RETRIES,
        "needs_int",
    )
    assert (
        stop.refusal
        == "Input should be a valid integer, unable to parse string as an integer"
    )
    assert "```" not in stop.render()
