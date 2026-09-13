"""What the thread records about each enrichment a worker answers."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from assistant_core.graph.turn_state import (
    DurableCall,
    DurableTaskResult,
    PendingDurableCall,
)
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, UserPromptPart
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph._lead_turn import resolve_turn_resumption
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession

_TASK_ID = UUID("0c6100d2-0000-4000-8000-000000000001")
_HISTORY = ModelMessagesTypeAdapter.dump_json(
    [ModelRequest(parts=[UserPromptPart(content="run GO enrichment on my set")])],
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
        user_prompt="run GO enrichment on my set",
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


def _enrichment_park(gene_set_id: str) -> PendingDurableCall:
    """The Lead's own enrichment call, parked on the task that answers it."""
    return PendingDurableCall(
        phase="lead",
        tool_call_id="call_enrich",
        tool_name="run_gene_set_enrichment",
        tool_args={"gene_set_id": gene_set_id},
        prior_messages_json=_HISTORY,
        durable_calls=[
            DurableCall(
                tool_call_id="call_enrich",
                tool_name="run_gene_set_enrichment",
                args={"gene_set_id": gene_set_id},
                task_id=_TASK_ID,
                durable_tool_name="geneset_enrichment",
            ),
        ],
    )


async def test_a_failed_enrichment_records_the_set_it_could_not_run_on() -> None:
    state = _state()
    state.pending_durable_call = _enrichment_park("gs-requested")
    state.durable_result = DurableTaskResult(
        task_id=_TASK_ID,
        status="failed",
        error="the gene set has no WDK step",
    )
    deps = _deps(state)

    await resolve_turn_resumption(state=state, deps=deps)

    assert [
        (run.gene_set_id, run.gene_set_name, run.succeeded)
        for run in deps.state.turn_markers.enrichment_runs
    ] == [("gs-requested", "", False)]


async def test_a_completed_enrichment_records_the_set_it_ran_on() -> None:
    state = _state()
    state.pending_durable_call = _enrichment_park("gs-other")
    state.durable_result = DurableTaskResult(
        task_id=_TASK_ID,
        status="success",
        result={
            "geneSetId": "gs-other",
            "geneSetName": "WDK Strategy 214617320",
            "geneCount": 155,
        },
    )
    deps = _deps(state)

    await resolve_turn_resumption(state=state, deps=deps)

    assert [
        (run.gene_set_id, run.gene_set_name, run.succeeded)
        for run in deps.state.turn_markers.enrichment_runs
    ] == [("gs-other", "WDK Strategy 214617320", True)]


async def test_a_carried_over_call_is_recorded_once() -> None:
    """A re-parked call travels to the next park; its record does not double."""
    state = _state()
    state.pending_durable_call = _enrichment_park("gs-own")
    state.durable_result = DurableTaskResult(
        task_id=_TASK_ID,
        status="success",
        result={"geneSetId": "gs-own"},
    )
    deps = _deps(state)

    await resolve_turn_resumption(state=state, deps=deps)
    await resolve_turn_resumption(state=state, deps=deps)

    assert [
        (run.task_id, run.gene_set_id)
        for run in deps.state.turn_markers.enrichment_runs
    ] == [(_TASK_ID, "gs-own")]
