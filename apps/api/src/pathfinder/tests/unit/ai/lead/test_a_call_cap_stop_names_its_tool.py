"""A pass the guard stops on a tool's call budget says so, and names the tool."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest
from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from pydantic_ai import RunContext, Tool
from pydantic_ai.toolsets import FunctionToolset

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import sub_agent_stream
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.dispatch_messages import stop_phrase
from pathfinder.ai.lead.frame_dispatch import frame_work_order
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import PhaseRun, stream_sub_agent
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    CLEAN_REPLY,
    reading_deps,
    reply,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    endless_tool_call_model,
    lead_deps,
    pipeline_state,
)

A_CAP_STOP = PhaseStop(
    role="verification",
    reason=PhaseStopReason.CALL_CAP,
    tool_calls=11,
    tool_name="read_gene_record",
)


async def read_one(ctx: RunContext[AgentDeps]) -> str:
    del ctx
    return "a record"


@pytest.fixture
def reading_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        sub_agent_stream, "phase_override_kwargs", lambda runtime, role: {}
    )
    with pinned_sub_agent(
        monkeypatch,
        "frame",
        model=endless_tool_call_model("read_one"),
        toolsets=[FunctionToolset[AgentDeps](tools=[Tool(read_one)])],
        instructions="Call the tool.",
    ):
        yield


def test_the_stop_names_the_budget_and_the_tool() -> None:
    assert A_CAP_STOP.render() == (
        "the verification pass stopped past its call budget for "
        "read_gene_record after 11 calls"
    )


def test_a_continuation_names_the_budget_and_the_tool() -> None:
    assert stop_phrase(A_CAP_STOP) == (
        "stopped past its call budget for read_gene_record"
    )


def test_a_repeated_call_keeps_its_own_words() -> None:
    stop = A_CAP_STOP.model_copy(update={"reason": PhaseStopReason.REPEATED_CALL})

    assert stop.render() == (
        "the verification pass stopped after repeating one call after 11 calls"
    )


@pytest.mark.usefixtures("collector", "reading_frame")
async def test_a_pass_stopped_on_a_cap_records_the_cap_and_its_tool() -> None:
    deps = lead_deps(pipeline_state(user_prompt="Find the kinases."))
    agent_deps = agent_deps_for(deps)
    agent_deps.tool_repetition_guard = ToolRepetitionGuard(call_caps={"read_one": 2})

    delta = await stream_sub_agent(
        run=PhaseRun("frame", frame_work_order("bind the criteria", deps), 3),
        agent_deps=agent_deps,
        parent_tool_call_id="call_frame_1",
        expected_output_type=FrameResult,
        deps=deps,
    )

    assert delta is None
    stop = deps.last_phase_stop
    assert stop is not None
    assert stop.reason is PhaseStopReason.CALL_CAP
    assert stop.tool_name == "read_one"
    assert stop.tool_calls == 2


def test_the_reply_after_a_cap_stop_is_held_to_state_it() -> None:
    deps = reading_deps()
    deps.last_phase_stop = A_CAP_STOP
    record = turn_record(replace(run_context_for(deps), retries={}))

    found = [(m.kind, m.sentence) for m in reconcile(reply(CLEAN_REPLY), record)]

    assert [kind for kind, _ in found] == ["unfinished_work", "stopped_check"]
    assert all("past its call budget for read_gene_record" in s for _, s in found)
