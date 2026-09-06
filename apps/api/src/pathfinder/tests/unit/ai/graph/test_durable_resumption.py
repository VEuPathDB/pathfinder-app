"""The parked durable call, and the results the completion turn resumes with."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import (
    DurableCall,
    DurableDeferral,
    DurableTaskResult,
    PendingDurableCall,
    SubAgentApprovalCall,
    SubAgentApprovalPending,
)
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ToolCallPart,
    ToolReturn,
    UserPromptPart,
)
from pydantic_ai.tools import DeferredToolRequests
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.graph._lead_turn import (
    ConcurrentDurableDispatchError,
    pending_durable_call,
    resolve_turn_resumption,
)
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, SubAgentDurablePark
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService

_TASK_ID = UUID("0c6100d2-0000-4000-8000-000000000001")
_HISTORY = ModelMessagesTypeAdapter.dump_json(
    [ModelRequest(parts=[UserPromptPart(content="compare febrile and normal")])],
).decode()


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="compare febrile and normal",
        user_message_id=uuid4(),
    )


def _deps(state: PipelineState) -> LeadDeps:
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=_quota_offline,
        web_search_service=WebSearchService(),
        literature_search_service=LiteratureSearchService(),
        cancel_event=asyncio.Event(),
    )
    return LeadDeps(state=state, intent=None, runtime=context, retrieved_memories=[])


def _call(tool_call_id: str, tool_name: str = "run_eda_compute") -> ToolCallPart:
    return ToolCallPart(
        tool_name=tool_name,
        args={"method": "DESeq"},
        tool_call_id=tool_call_id,
    )


def _parked(*, sub_agent: SubAgentApprovalPending | None = None) -> PendingDurableCall:
    inner = "call_compute" if sub_agent is None else sub_agent.approvals[0].tool_call_id
    return PendingDurableCall(
        phase="lead" if sub_agent is None else "verification",
        tool_call_id="call_compute",
        tool_name="run_eda_compute",
        tool_args={"method": "DESeq"},
        prior_messages_json=_HISTORY,
        durable_calls=[
            DurableCall(
                tool_call_id=inner,
                tool_name="run_eda_compute",
                args={"method": "DESeq"},
                task_id=_TASK_ID,
                durable_tool_name="run_eda_compute",
            ),
        ],
        sub_agent=sub_agent,
    )


def test_the_parked_call_carries_the_task_and_the_registered_tool_name() -> None:
    state = _state()
    deps = _deps(state)
    deps.durable_deferrals["call_enrich"] = DurableDeferral(
        task_id=_TASK_ID,
        tool_name="geneset_enrichment",
    )
    output = DeferredToolRequests(
        calls=[_call("call_enrich", "run_gene_set_enrichment")],
    )

    parked = pending_durable_call(output=output, deps=deps, messages=[])

    assert parked is not None
    assert parked.task_ids == [_TASK_ID]
    assert parked.tool_call_id == "call_enrich"
    assert parked.tool_name == "run_gene_set_enrichment"
    assert [c.durable_tool_name for c in parked.durable_calls] == ["geneset_enrichment"]
    assert parked.phase == "lead"


def test_two_durable_lead_calls_in_one_response_are_both_parked() -> None:
    state = _state()
    deps = _deps(state)
    tasks = {"call_a": uuid4(), "call_b": uuid4()}
    for call_id, task_id in tasks.items():
        deps.durable_deferrals[call_id] = DurableDeferral(
            task_id=task_id,
            tool_name="run_eda_compute",
        )
    output = DeferredToolRequests(calls=[_call("call_a"), _call("call_b")])

    parked = pending_durable_call(output=output, deps=deps, messages=[])

    assert parked is not None
    assert [c.tool_call_id for c in parked.durable_calls] == ["call_a", "call_b"]
    assert parked.task_ids == [tasks["call_a"], tasks["call_b"]]
    assert parked.owns(tasks["call_b"]) is True


def test_two_sub_agent_dispatches_with_durable_calls_are_refused() -> None:
    state = _state()
    deps = _deps(state)
    for call_id in ("call_a", "call_b"):
        deps.pending_sub_agent_durables[call_id] = SubAgentDurablePark(
            pending=SubAgentApprovalPending(
                role="verification",
                approvals=[
                    SubAgentApprovalCall(
                        tool_call_id=f"inner_{call_id}",
                        tool_name="run_eda_compute",
                    ),
                ],
                messages_json=_HISTORY,
            ),
            deferrals={
                f"inner_{call_id}": DurableDeferral(
                    task_id=_TASK_ID,
                    tool_name="run_eda_compute",
                ),
            },
        )
    output = DeferredToolRequests(calls=[_call("call_a"), _call("call_b")])

    with pytest.raises(ConcurrentDurableDispatchError, match="call_a, call_b"):
        pending_durable_call(output=output, deps=deps, messages=[])


def test_a_call_no_worker_holds_is_not_a_durable_park() -> None:
    state = _state()
    deps = _deps(state)
    output = DeferredToolRequests(calls=[_call("call_verify", "verify_strategy")])

    assert pending_durable_call(output=output, deps=deps, messages=[]) is None


async def test_the_completion_turn_answers_the_parked_call_id() -> None:
    state = _state()
    state.pending_durable_call = _parked()
    state.durable_result = DurableTaskResult(
        task_id=_TASK_ID,
        status="success",
        result={"genesTested": 5511, "retainedUp": 529, "retainedDown": 1014},
    )

    resumption = await resolve_turn_resumption(state=state, deps=_deps(state))

    assert resumption.parked is state.pending_durable_call
    assert resumption.results is not None
    answer = resumption.results.calls["call_compute"]
    assert isinstance(answer, ToolReturn)
    assert answer.return_value == {
        "status": "success",
        "result": {"genesTested": 5511, "retainedUp": 529, "retainedDown": 1014},
    }
    summaries = [
        chunk
        for chunk in (answer.metadata or [])
        if getattr(chunk, "type", "") == "data-tool-summary"
    ]
    assert len(summaries) == 1


async def test_a_failed_job_reaches_the_model_as_a_failed_result() -> None:
    state = _state()
    state.pending_durable_call = _parked()
    state.durable_result = DurableTaskResult(
        task_id=_TASK_ID,
        status="failed",
        error="EDA compute job no-such-job failed",
    )

    resumption = await resolve_turn_resumption(state=state, deps=_deps(state))

    assert resumption.results is not None
    answer = resumption.results.calls["call_compute"]
    assert isinstance(answer, ToolReturn)
    assert answer.return_value == {
        "status": "failed",
        "error": "EDA compute job no-such-job failed",
    }
    assert answer.metadata == []


async def test_a_result_for_another_task_leaves_the_call_parked() -> None:
    state = _state()
    state.pending_durable_call = _parked()
    state.durable_result = DurableTaskResult(task_id=uuid4(), status="success")

    resumption = await resolve_turn_resumption(state=state, deps=_deps(state))

    assert resumption.parked is None
    assert resumption.results is None
    assert state.resumes_parked_call is False


def test_the_sub_agent_park_names_the_inner_call_the_worker_answers() -> None:
    parked = _parked(
        sub_agent=SubAgentApprovalPending(
            role="verification",
            approvals=[
                SubAgentApprovalCall(
                    tool_call_id="call_enrich",
                    tool_name="run_gene_set_enrichment",
                ),
            ],
            messages_json=_HISTORY,
        ),
    )

    assert [c.tool_call_id for c in parked.durable_calls] == ["call_enrich"]


def test_a_lead_park_names_its_own_call() -> None:
    assert [c.tool_call_id for c in _parked().durable_calls] == ["call_compute"]
