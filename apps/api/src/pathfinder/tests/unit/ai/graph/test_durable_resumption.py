"""The parked durable call, and the results the completion turn resumes with."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from assistant_core.graph import approvals
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
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph import _lead_turn
from pathfinder.ai.graph._lead_durable import (
    ConcurrentDurableDispatchError,
    durable_resume_hints,
    pending_durable_call,
)
from pathfinder.ai.graph._lead_turn import resolve_turn_resumption
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_resume import SubAgentOutcome
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, SubAgentDurablePark
from pathfinder.domain.strategy.session import StrategySession

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


_OWN_TASK_ID = UUID("0c6100d2-0000-4000-8000-000000000002")
_NEXT_TASK_ID = UUID("0c6100d2-0000-4000-8000-000000000003")


def _mixed_park() -> PendingDurableCall:
    """One park: a dispatch's inner call, and the Lead's own call beside it."""
    return PendingDurableCall(
        phase="verification",
        tool_call_id="call_verify",
        tool_name="verify_strategy",
        tool_args={"reason": "check the build"},
        prior_messages_json=_HISTORY,
        durable_calls=[
            DurableCall(
                tool_call_id="inner_enrich",
                tool_name="run_gene_set_enrichment",
                args={"gene_set_id": "gs-inner"},
                task_id=_TASK_ID,
                durable_tool_name="geneset_enrichment",
            ),
            DurableCall(
                tool_call_id="call_enrich",
                tool_name="run_gene_set_enrichment",
                args={"gene_set_id": "gs-own"},
                task_id=_OWN_TASK_ID,
                durable_tool_name="geneset_enrichment",
            ),
        ],
        sub_agent=SubAgentApprovalPending(
            role="verification",
            approvals=[
                SubAgentApprovalCall(
                    tool_call_id="inner_enrich",
                    tool_name="run_gene_set_enrichment",
                ),
            ],
            messages_json=_HISTORY,
        ),
    )


def _both_reported() -> list[DurableTaskResult]:
    return [
        DurableTaskResult(
            task_id=_TASK_ID,
            status="success",
            result={"geneSetId": "gs-inner", "geneCount": 155},
        ),
        DurableTaskResult(
            task_id=_OWN_TASK_ID,
            status="success",
            result={"geneSetId": "gs-own", "geneCount": 42},
        ),
    ]


def test_a_dispatch_and_a_lead_durable_call_are_parked_together() -> None:
    """Both deferred calls sit in one park, so both can be answered."""
    state = _state()
    deps = _deps(state)
    deps.pending_sub_agent_durables["call_verify"] = SubAgentDurablePark(
        pending=SubAgentApprovalPending(
            role="verification",
            approvals=[
                SubAgentApprovalCall(
                    tool_call_id="inner_enrich",
                    tool_name="run_gene_set_enrichment",
                ),
            ],
            messages_json=_HISTORY,
        ),
        deferrals={
            "inner_enrich": DurableDeferral(
                task_id=_TASK_ID,
                tool_name="geneset_enrichment",
            ),
        },
    )
    deps.durable_deferrals["call_enrich"] = DurableDeferral(
        task_id=_OWN_TASK_ID,
        tool_name="geneset_enrichment",
    )
    output = DeferredToolRequests(
        calls=[
            _call("call_verify", "verify_strategy"),
            _call("call_enrich", "run_gene_set_enrichment"),
        ],
    )

    parked = pending_durable_call(output=output, deps=deps, messages=[])

    assert parked is not None
    assert parked.tool_call_id == "call_verify"
    assert parked.sub_agent is not None
    assert [c.tool_call_id for c in parked.durable_calls] == [
        "inner_enrich",
        "call_enrich",
    ]
    assert parked.task_ids == [_TASK_ID, _OWN_TASK_ID]


async def test_each_parked_call_is_answered_once_on_the_completion_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sub-agent gets its own call; the Lead gets its own and the delta."""
    state = _state()
    state.pending_durable_call = _mixed_park()
    state.durable_results = _both_reported()
    handed: list[DeferredToolResults] = []

    async def _resume(
        *, deps: LeadDeps, approval: PendingDurableCall, resume: SubAgentResume
    ) -> SubAgentOutcome:
        del deps, approval
        handed.append(resume.results)
        return FrameResult(summary="verified")

    monkeypatch.setattr(_lead_turn, "resume_sub_agent", _resume)

    resumption = await resolve_turn_resumption(state=state, deps=_deps(state))

    assert [sorted(results.calls) for results in handed] == [["inner_enrich"]]
    assert resumption.results is not None
    assert sorted(resumption.results.calls) == ["call_enrich", "call_verify"]
    own = resumption.results.calls["call_enrich"]
    assert isinstance(own, ToolReturn)
    assert own.return_value == {
        "status": "success",
        "result": {"geneSetId": "gs-own", "geneCount": 42},
    }


async def test_a_sub_agent_that_parks_again_carries_the_leads_answered_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Lead's call travels to the new park, so its result is not lost."""
    state = _state()
    state.pending_durable_call = _mixed_park()
    state.durable_results = _both_reported()

    async def _resume(
        *, deps: LeadDeps, approval: PendingDurableCall, resume: SubAgentResume
    ) -> SubAgentOutcome:
        del deps, approval, resume
        return SubAgentApprovalWait(
            pending=SubAgentApprovalPending(
                role="verification",
                approvals=[
                    SubAgentApprovalCall(
                        tool_call_id="inner_next",
                        tool_name="run_gene_set_enrichment",
                    ),
                ],
                messages_json=_HISTORY,
            ),
            durable={
                "inner_next": DurableDeferral(
                    task_id=_NEXT_TASK_ID,
                    tool_name="geneset_enrichment",
                ),
            },
        )

    monkeypatch.setattr(_lead_turn, "resume_sub_agent", _resume)

    resumption = await resolve_turn_resumption(state=state, deps=_deps(state))

    assert resumption.still_durable is not None
    assert [c.tool_call_id for c in resumption.still_durable.durable_calls] == [
        "inner_next",
        "call_enrich",
    ]
    assert resumption.still_durable.task_ids == [_NEXT_TASK_ID, _OWN_TASK_ID]


def test_a_call_no_worker_holds_is_not_a_durable_park() -> None:
    state = _state()
    deps = _deps(state)
    output = DeferredToolRequests(calls=[_call("call_verify", "verify_strategy")])

    assert pending_durable_call(output=output, deps=deps, messages=[]) is None


_COMPUTE_RESULT = {
    "genesTested": 5511,
    "retainedUp": 529,
    "retainedDown": 1014,
    "comparison": {"groupA": ["normal"], "groupB": ["febrile"]},
}


async def test_the_completion_turn_answers_the_parked_call_id() -> None:
    state = _state()
    state.pending_durable_call = _parked()
    state.durable_result = DurableTaskResult(
        task_id=_TASK_ID,
        status="success",
        result=_COMPUTE_RESULT,
    )

    resumption = await resolve_turn_resumption(state=state, deps=_deps(state))

    assert resumption.parked is state.pending_durable_call
    assert resumption.results is not None
    answer = resumption.results.calls["call_compute"]
    assert isinstance(answer, ToolReturn)
    assert answer.return_value == {
        "status": "success",
        "result": _COMPUTE_RESULT,
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


def test_a_lead_only_park_is_announced_the_way_the_runtime_announces_it() -> None:
    parked = _parked()

    assert durable_resume_hints(parked) == approvals.durable_hints(parked)


def test_a_mixed_park_announces_the_dispatch_and_the_leads_own_calls() -> None:
    """The dispatch stands for its inner calls; the Lead's own are named."""
    parked = _mixed_park()

    assert [hint.tool_call_id for hint in durable_resume_hints(parked)] == [
        "call_verify",
        "call_enrich",
    ]
