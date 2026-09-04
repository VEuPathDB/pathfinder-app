"""An approval-required tool inside a sub-agent reaches the user and comes back.

The sub-agent run stops with ``DeferredToolRequests``; the dispatch forwards the
inner call as a tool part, waits, and the user's answer re-enters the same run.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai import Agent, DeferredToolRequests, RunContext, Tool
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelResponse,
    ToolCallPart,
)
from pydantic_ai.tools import DeferredToolResults, ToolDenied
from pydantic_ai.toolsets import FunctionToolset

from pathfinder.ai.agents.execution import EXECUTION_MODEL, ExecutionAgent
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.deltas import FrameResult, RecoveryDelta
from pathfinder.ai.lead.dispatch_resume import resume_sub_agent
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_dispatch import run_recovery
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, SubAgentRunUsage
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.toolsets import execution, verification
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    call_then_final_model,
    lead_deps,
    pipeline_state,
)

_OPTIMIZE_ARGS: dict[str, Any] = {
    "target": {
        "site_id": "plasmodb",
        "record_type": "transcript",
        "search_name": "GenesByRNASeqEvidence",
        "parameter_space": [
            {"name": "min_fold_change", "kind": "numeric", "low": 1.5, "high": 4.0},
        ],
    },
    "controls": {
        "positive_controls": ["PF3D7_1133400"],
        "negative_controls": ["PF3D7_0930300"],
    },
    "settings": {"budget": 8, "objective": "f1"},
}
_DELETE_ARGS: dict[str, Any] = {"step_id": "s2"}
_VERIFICATION_FINAL: dict[str, Any] = {
    "digest": {
        "disposition": "done",
        "prose": "scripted",
        "reason": "scripted",
        "success": True,
    },
}
_RECOVERY_FINAL: dict[str, Any] = {
    "actionsTaken": ["deleted s2"],
    "followUpNeeded": False,
}

_TEST_INSTRUCTIONS = "Call the tool the script names, then return the typed output."


def _deps(usage_log: list[SubAgentRunUsage] | None = None) -> LeadDeps:
    state = pipeline_state(
        user_prompt="Tune the RNA-Seq fold change against my controls.",
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1", "s2"],
        failed_steps=[],
        root_count=0,
    )
    recorded = usage_log if usage_log is not None else []
    return lead_deps(state, record_usage=recorded.append)


@pytest.fixture
def deleted_step_ids() -> list[str]:
    return []


@pytest.fixture
def scripted_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: call_then_final_model("delete_step", _DELETE_ARGS, _RECOVERY_FINAL),
    )


def _delete_step_toolset(recorded: list[str]) -> FunctionToolset[AgentDeps]:
    async def delete_step(ctx: RunContext[AgentDeps], step_id: str) -> str:
        del ctx
        recorded.append(step_id)
        return f"deleted {step_id}"

    return FunctionToolset[AgentDeps](
        tools=[Tool(delete_step, requires_approval=True)],
    )


@pytest.fixture
def stub_execution_toolset(
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> Iterator[None]:
    """The execution agent with one approval-gated tool that records its calls."""
    with pinned_sub_agent(
        monkeypatch,
        "execution",
        toolsets=[_delete_step_toolset(deleted_step_ids)],
        instructions=_TEST_INSTRUCTIONS,
    ):
        yield


async def _recover(deps: LeadDeps, resume: SubAgentResume | None = None) -> object:
    return await run_recovery(
        deps=deps,
        parent_tool_call_id="lead_call_recover",
        reason="drop the step that failed to push",
        resume=resume,
    )


def _approval_resume(
    waiting: SubAgentApprovalWait,
    results: DeferredToolResults,
) -> SubAgentResume:
    return SubAgentResume(
        messages=ModelMessagesTypeAdapter.validate_json(
            waiting.pending.messages_json,
        ),
        results=results,
    )


async def test_verification_approval_reaches_the_client(
    collector: ChunkCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: call_then_final_model(
            "optimize_search_parameters", _OPTIMIZE_ARGS, _VERIFICATION_FINAL
        ),
    )
    deps = _deps()

    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions=_TEST_INSTRUCTIONS,
    ):
        result = await run_verification(
            deps=deps,
            parent_tool_call_id="lead_call_verify",
            reason="optimize the RNA-Seq fold change against the controls",
        )

    assert isinstance(result, SubAgentApprovalWait)
    assert result.pending.role == "verification"
    call = result.pending.approvals[0]
    assert call.tool_name == "optimize_search_parameters"
    assert call.tool_call_id == "call_optimize_search_parameters"
    assert call.args["settings"] == {"budget": 8, "objective": "f1"}

    started = collector.chunks_of("tool-input-start")
    assert [c["toolCallId"] for c in started] == ["call_optimize_search_parameters"]
    assert started[0]["toolName"] == "optimize_search_parameters"
    available = collector.chunks_of("tool-input-available")
    assert available[0]["input"]["target"]["search_name"] == "GenesByRNASeqEvidence"
    assert collector.chunks_of("tool-approval-request") == [
        {
            "type": "tool-approval-request",
            "approvalId": "call_optimize_search_parameters",
            "toolCallId": "call_optimize_search_parameters",
        },
    ]

    replay = ModelMessagesTypeAdapter.validate_json(result.pending.messages_json)
    assert any(
        part.tool_name == "optimize_search_parameters"
        for msg in replay
        if isinstance(msg, ModelResponse)
        for part in msg.parts
        if isinstance(part, ToolCallPart)
    )


@pytest.mark.usefixtures("scripted_delete")
async def test_execution_approval_reaches_the_client(
    collector: ChunkCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps()

    with pinned_sub_agent(
        monkeypatch,
        "execution",
        toolsets=[execution.build_toolset()],
        instructions=_TEST_INSTRUCTIONS,
    ):
        result = await _recover(deps)

    assert isinstance(result, SubAgentApprovalWait)
    assert result.pending.role == "execution"
    call = result.pending.approvals[0]
    assert (call.tool_name, call.tool_call_id) == ("delete_step", "call_delete_step")
    assert call.args == {"step_id": "s2"}
    assert collector.chunks_of("tool-approval-request")[0]["approvalId"] == (
        "call_delete_step"
    )


@pytest.mark.usefixtures("scripted_delete", "collector")
async def test_a_resumed_dispatch_runs_on_a_freshly_built_agent(
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    """The answer re-enters from the stored messages, so the second half of a
    dispatch runs on the agent that half built."""
    built: list[ExecutionAgent] = []

    def build() -> ExecutionAgent:
        agent: ExecutionAgent = Agent(
            EXECUTION_MODEL,
            output_type=[RecoveryDelta, DeferredToolRequests],
            deps_type=AgentDeps,
            instructions=_TEST_INSTRUCTIONS,
            toolsets=[_delete_step_toolset(deleted_step_ids)],
            name="execution",
            defer_model_check=True,
        )
        built.append(agent)
        return agent

    monkeypatch.setitem(sub_agent_tools.BUILD_SUB_AGENT_BY_ROLE, "execution", build)
    deps = _deps()

    waiting = await _recover(deps)
    assert isinstance(waiting, SubAgentApprovalWait)

    resumed = await _recover(
        deps,
        _approval_resume(
            waiting, DeferredToolResults(approvals={"call_delete_step": True})
        ),
    )

    assert isinstance(resumed, RecoveryDelta)
    assert deleted_step_ids == ["s2"]
    assert len(built) == 2
    assert built[0] is not built[1]


@pytest.mark.usefixtures("stub_execution_toolset", "scripted_delete")
async def test_approval_runs_the_inner_tool_and_returns_the_delta(
    collector: ChunkCollector,
    deleted_step_ids: list[str],
) -> None:
    usage_log: list[SubAgentRunUsage] = []
    deps = _deps(usage_log)

    waiting = await _recover(deps)
    assert isinstance(waiting, SubAgentApprovalWait)
    assert deleted_step_ids == []

    resumed = await _recover(
        deps,
        _approval_resume(
            waiting, DeferredToolResults(approvals={"call_delete_step": True})
        ),
    )

    assert isinstance(resumed, RecoveryDelta)
    assert resumed.actions_taken == ["deleted s2"]
    assert deleted_step_ids == ["s2"]
    outputs = collector.chunks_of("tool-output-available")
    assert [c["toolCallId"] for c in outputs] == ["call_delete_step"]
    # Each half of the dispatch is charged once, under the Lead's call id.
    assert [u.parent_tool_call_id for u in usage_log] == [
        "lead_call_recover",
        "lead_call_recover",
    ]
    assert all(u.usage.total_tokens > 0 for u in usage_log)


@pytest.mark.usefixtures("stub_execution_toolset", "scripted_delete")
async def test_denial_finishes_the_sub_agent_without_running_the_tool(
    collector: ChunkCollector,
    deleted_step_ids: list[str],
) -> None:
    deps = _deps()

    waiting = await _recover(deps)
    assert isinstance(waiting, SubAgentApprovalWait)

    resumed = await _recover(
        deps,
        _approval_resume(
            waiting,
            DeferredToolResults(
                approvals={
                    "call_delete_step": ToolDenied(message="Keep that step."),
                },
            ),
        ),
    )

    assert isinstance(resumed, RecoveryDelta)
    assert deleted_step_ids == []
    denied = collector.chunks_of("tool-output-denied")
    assert [c["toolCallId"] for c in denied] == ["call_delete_step"]
    # A tool the user refused reads "denied", not "completed" and not "failed".
    steps = [
        data
        for data in collector.data_of("data-sub-agent-step")
        if data.get("toolCallId") == "call_delete_step"
    ]
    assert [step["state"] for step in steps] == ["started", "started", "denied"]
    assert "Keep that step." in steps[-1]["resultSummary"]


async def test_the_stored_dispatch_arguments_drive_the_re_entry(
    collector: ChunkCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frame dispatch resumes from what the checkpoint holds: its tool
    name and the arguments the Lead called it with."""
    bound_criteria: list[str] = []

    async def bind_criterion(ctx: RunContext[AgentDeps], criterion_id: str) -> str:
        # A spec_ready result is refused unless the draft records the binding.
        ctx.deps.agent_state.frame_set_criterion(
            Criterion(
                id=criterion_id,
                text="the criterion the run bound",
                search_name="GenesByText",
            )
        )
        bound_criteria.append(criterion_id)
        return f"bound {criterion_id}"

    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: call_then_final_model(
            "bind_criterion",
            {"criterion_id": "c1"},
            {"summary": "bound one", "disposition": "spec_ready"},
        ),
    )
    deps = _deps()
    toolset = FunctionToolset[AgentDeps](
        tools=[Tool(bind_criterion, requires_approval=True)],
    )

    with pinned_sub_agent(
        monkeypatch,
        "frame",
        toolsets=[toolset],
        instructions=_TEST_INSTRUCTIONS,
    ):
        waiting = await run_frame(
            deps=deps,
            parent_tool_call_id="lead_call_frame",
            work_order=frame_work_order("operationalize the goal", ""),
            expected_criteria=5,
        )
        assert isinstance(waiting, SubAgentApprovalWait)
        assert waiting.pending.role == "frame"
        assert bound_criteria == []

        resumed = await resume_sub_agent(
            deps=deps,
            approval=PendingApproval(
                phase="frame",
                tool_call_id="lead_call_frame",
                tool_name="frame_problem",
                tool_args={"reason": "operationalize the goal", "expected_criteria": 5},
                sub_agent=waiting.pending,
            ),
            resume=_approval_resume(
                waiting,
                DeferredToolResults(approvals={"call_bind_criterion": True}),
            ),
        )

    assert isinstance(resumed, FrameResult)
    assert resumed.summary == "bound one"
    assert bound_criteria == ["c1"]
    assert [c["toolCallId"] for c in collector.chunks_of("tool-output-available")] == [
        "call_bind_criterion",
    ]
