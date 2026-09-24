"""The durable calls one Lead response parks, and how their answers divide.

A response can defer a sub-agent dispatch and calls of the Lead's own together.
One park carries both groups; the sub-agent's group is named by the calls it
suspended on, and the rest belong to the Lead's own run.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from assistant_core.conversation.vercel_adapter import DeferredToolHint
from assistant_core.graph import approvals
from assistant_core.graph.turn_state import (
    DurableCall,
    DurableDeferral,
    DurableTaskResult,
    PendingDurableCall,
    SubAgentApprovalPending,
)
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, JsonValue
from pydantic_ai.messages import ModelMessage
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults

from pathfinder.ai.graph.turn_records import EnrichmentRun
from pathfinder.ai.lead.sub_agent_tools import WIRE_PHASE_BY_ROLE, LeadDeps

_ENRICHMENT_TOOL = "run_gene_set_enrichment"

__all__ = [
    "ConcurrentDurableDispatchError",
    "durable_resume_hints",
    "enrichment_runs_answered",
    "inner_durable_calls",
    "outer_durable_calls",
    "pending_durable_call",
    "split_durable_answers",
]


class _EnrichmentArgs(BaseModel):
    """The gene set one enrichment call was made for."""

    model_config = ConfigDict(extra="ignore")

    gene_set_id: str = ""


class _EnrichmentReport(CamelModel):
    """The gene set one finished enrichment says it analysed."""

    model_config = ConfigDict(extra="ignore")

    gene_set_id: str = ""
    gene_set_name: str = ""


def enrichment_runs_answered(
    parked: PendingDurableCall,
    answers: Mapping[UUID, DurableTaskResult],
) -> list[EnrichmentRun]:
    """What each answered enrichment ran on, as the thread records it."""
    runs: list[EnrichmentRun] = []
    for call in parked.durable_calls:
        if call.tool_name != _ENRICHMENT_TOOL:
            continue
        answer = answers[call.task_id]
        reported = _EnrichmentReport.model_validate(answer.result)
        asked = _EnrichmentArgs.model_validate(call.args)
        runs.append(
            EnrichmentRun(
                task_id=call.task_id,
                gene_set_id=reported.gene_set_id or asked.gene_set_id,
                gene_set_name=reported.gene_set_name,
                succeeded=answer.status == "success",
            ),
        )
    return runs


class ConcurrentDurableDispatchError(RuntimeError):
    """Two sub-agent dispatches in one Lead response both parked durable calls."""

    def __init__(self, tool_call_ids: list[str]) -> None:
        super().__init__(
            "Two sub-agent dispatches deferred durable calls in one response "
            f"({', '.join(tool_call_ids)}). One suspended run is checkpointed "
            "per turn, so the second would be re-run rather than resumed.",
        )


def _durable_call(
    *,
    tool_call_id: str,
    tool_name: str,
    args: dict[str, JsonValue],
    deferral: DurableDeferral,
) -> DurableCall:
    return DurableCall(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        args=args,
        task_id=deferral.task_id,
        durable_tool_name=deferral.tool_name,
    )


def inner_durable_calls(
    pending: SubAgentApprovalPending,
    deferrals: dict[str, DurableDeferral],
) -> list[DurableCall]:
    """The calls a sub-agent parked, each bound to the task that answers it."""
    return [
        _durable_call(
            tool_call_id=inner.tool_call_id,
            tool_name=inner.tool_name,
            args=inner.args,
            deferral=deferrals[inner.tool_call_id],
        )
        for inner in pending.approvals
    ]


def outer_durable_calls(parked: PendingDurableCall) -> list[DurableCall]:
    """The parked calls the Lead made itself, which its own run answers."""
    sub_agent = parked.sub_agent
    if sub_agent is None:
        return list(parked.durable_calls)
    inner = {call.tool_call_id for call in sub_agent.approvals}
    return [call for call in parked.durable_calls if call.tool_call_id not in inner]


def split_durable_answers(
    parked: PendingDurableCall,
    answered: DeferredToolResults,
) -> tuple[DeferredToolResults, DeferredToolResults]:
    """The answers the sub-agent resumes with, and the ones the Lead does."""
    own = {call.tool_call_id for call in outer_durable_calls(parked)}
    return (
        DeferredToolResults(
            calls={k: v for k, v in answered.calls.items() if k not in own},
        ),
        DeferredToolResults(
            calls={k: v for k, v in answered.calls.items() if k in own},
        ),
    )


def durable_resume_hints(parked: PendingDurableCall) -> list[DeferredToolHint]:
    """What the resumed stream re-announces for this park.

    A sub-agent's inner calls are rendered by the dispatch that ran them, so
    the dispatch stands for them; every other call is announced by itself.
    """
    hints = [
        DeferredToolHint(
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            tool_args=dict(call.args),
        )
        for call in outer_durable_calls(parked)
    ]
    if parked.sub_agent is None:
        return hints
    return [approvals.deferred_hint(parked), *hints]


def pending_durable_call(
    *,
    output: DeferredToolRequests,
    deps: LeadDeps,
    messages: list[ModelMessage],
) -> PendingDurableCall | None:
    """The durable calls a deferred Lead run waits on the worker for.

    They outrank an approval in the same response: their tasks are already
    running, and an unapproved Lead tool is re-collected by pydantic-ai on the
    next run. One suspended run is checkpointed per turn, so two dispatches
    cannot be parked together.
    """
    dispatches = [
        call
        for call in output.calls
        if call.tool_call_id in deps.pending_sub_agent_durables
    ]
    if len(dispatches) > 1:
        raise ConcurrentDurableDispatchError([c.tool_call_id for c in dispatches])
    own_parts = [
        call for call in output.calls if call.tool_call_id in deps.durable_deferrals
    ]
    own = [
        _durable_call(
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            args=call.args_as_dict(),
            deferral=deps.durable_deferrals[call.tool_call_id],
        )
        for call in own_parts
    ]
    if dispatches:
        park = deps.pending_sub_agent_durables[dispatches[0].tool_call_id]
        return approvals.parked_durable_call(
            call=dispatches[0],
            phase=WIRE_PHASE_BY_ROLE[park.pending.role],
            messages=messages,
            durable_calls=inner_durable_calls(park.pending, park.deferrals) + own,
            sub_agent=park.pending,
        )
    if not own:
        return None
    return approvals.parked_durable_call(
        call=own_parts[0],
        phase="lead",
        messages=messages,
        durable_calls=own,
    )
