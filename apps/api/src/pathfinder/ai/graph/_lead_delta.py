"""The state update one Lead turn writes back to the graph.

The node drives the run; this module turns what the run captured into the
delta LangGraph merges into the checkpoint.
"""

from __future__ import annotations

from typing import Any

from assistant_core.memory.schemas import MemoryValue

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.lead_agent import LeadResponse
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import OpenQuestion


def _open_questions(
    domain: StrategyDomainState, response: LeadResponse | None
) -> list[OpenQuestion]:
    """What this turn asked the user: the sub-agents' questions and the reply's.

    One question asked twice keeps the record that names the dimension it
    decides. A turn that ends parked asks nothing new, and a turn that resolves
    the investigation asks nothing at all.
    """
    if response is None:
        return list(domain.open_questions)
    if response.next_state == "complete":
        return []
    asked: list[OpenQuestion] = []
    index_of: dict[str, int] = {}
    for question in (*domain.open_questions, *response.asked_questions):
        if question.question not in index_of:
            index_of[question.question] = len(asked)
            asked.append(question)
            continue
        held = index_of[question.question]
        if question.decides_a_dimension and not asked[held].decides_a_dimension:
            asked[held] = question
    return asked


def _created_gene_sets(deps: LeadDeps) -> list[CreatedGeneSet]:
    """The gene sets whose note is still owed, with this turn's additions.

    A set is recorded once by id. The list is emptied when its notes reach the
    store, so the write does not grow with the thread.
    """
    recorded = {created.id: created for created in deps.state.domain.created_gene_sets}
    recorded.update({created.id: created for created in deps.created_gene_sets})
    return list(recorded.values())


def _domain_delta(
    *,
    deps: LeadDeps,
    capture: _LeadRunCapture,
) -> StrategyDomainState:
    domain = deps.state.domain
    response = capture.response
    return domain.model_copy(
        update={
            "user_intent": deps.intent,
            "discovered_searches": dict(domain.discovered_searches),
            "lead_next_state": (
                response.next_state if response is not None else domain.lead_next_state
            ),
            "open_questions": _open_questions(domain, response),
            "created_gene_sets": _created_gene_sets(deps),
            # Staleness is measured against the live strategy every turn.
            "stale_build": None,
        },
    )


def _build_state_delta(
    *,
    state: PipelineState,
    deps: LeadDeps,
    capture: _LeadRunCapture,
    memories: list[MemoryValue],
) -> dict[str, Any]:
    cumulative_tokens = (
        state.turn_total_tokens + capture.tokens + capture.sub_agent_tokens
    )
    cumulative_cost = (
        state.turn_total_cost_usd + capture.cost_usd + capture.sub_agent_cost
    )
    delta: dict[str, Any] = {
        "domain": _domain_delta(deps=deps, capture=capture),
        "retrieved_memories": memories,
        "turn_total_tokens": cumulative_tokens,
        "turn_total_cost_usd": cumulative_cost,
    }
    if capture.pending_approval is not None:
        delta["pending_approval"] = capture.pending_approval
    elif capture.parked_call_answered:
        delta["pending_approval"] = None
    if capture.pending_durable_call is not None:
        delta["pending_durable_call"] = capture.pending_durable_call
    elif state.pending_durable_call is not None and capture.parked_call_answered:
        delta["pending_durable_call"] = None
    return delta


__all__ = ["_build_state_delta", "_domain_delta"]
