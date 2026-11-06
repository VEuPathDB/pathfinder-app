from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from assistant_core.conversation.vercel_adapter import DeferredToolHint
from assistant_core.graph import approvals
from assistant_core.graph.durable import durable_tool_results
from assistant_core.graph.turn_state import (
    ParkedCall,
    PendingApproval,
    PendingDurableCall,
)
from assistant_core.memory.schemas import MemoryValue
from pydantic_ai.messages import ModelMessage, UserContent
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults

from pathfinder.ai.capabilities.metering import SpendMeter
from pathfinder.ai.explore.readings_card import card_labels
from pathfinder.ai.graph._lead_durable import pending_durable_call
from pathfinder.ai.graph._lead_exchange import _answer_words
from pathfinder.ai.graph._lead_turn import pending_approval
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.exchanges import Exchange
from pathfinder.domain.modes import EXPLORE_PHASE, READINGS_PHASE
from pathfinder.domain.strategy.chosen_reading import ChosenReading

_HAND_OVER_TOOL = "consult_user"


@dataclass(frozen=True)
class ExploreTurn:
    prompt: str | Sequence[UserContent] | None
    prompt_message_id: str | None
    history: list[ModelMessage] | None
    results: DeferredToolResults | None
    hints: tuple[DeferredToolHint, ...]
    answered: ParkedCall | None


def explore_turn_for(state: PipelineState) -> ExploreTurn:
    durable = state.answered_durable_call
    if durable is not None:
        return ExploreTurn(
            prompt=None,
            prompt_message_id=None,
            history=approvals.resume_history(durable),
            results=durable_tool_results(durable, state.durable_answers),
            hints=tuple(approvals.durable_hints(durable)),
            answered=durable,
        )
    approval = state.pending_approval
    if approval is not None:
        results = approvals.approval_results(approval, state.approval_responses)
        if results is not None:
            return ExploreTurn(
                prompt=None,
                prompt_message_id=None,
                history=approvals.resume_history(approval),
                results=results,
                hints=(approvals.deferred_hint(approval),),
                answered=approval,
            )
    message_id = state.user_message_id
    return ExploreTurn(
        prompt=state.user_content,
        prompt_message_id=None if message_id is None else str(message_id),
        history=None,
        results=None,
        hints=(),
        answered=None,
    )


def explore_park(
    output: DeferredToolRequests, deps: LeadDeps, messages: list[ModelMessage]
) -> PendingApproval | PendingDurableCall | None:
    durable = pending_durable_call(output=output, deps=deps, messages=messages)
    if durable is not None:
        return durable.model_copy(update={"phase": EXPLORE_PHASE})
    approval = pending_approval(output=output, deps=deps, messages=messages)
    if approval is None:
        return None
    phase = READINGS_PHASE if approval.tool_name == _HAND_OVER_TOOL else EXPLORE_PHASE
    return approval.model_copy(update={"phase": phase})


def hands_over(parked: ParkedCall) -> bool:
    return parked.phase == READINGS_PHASE


def hand_over_reading(domain: StrategyDomainState, park: ParkedCall) -> None:
    labels = card_labels(park.tool_args)
    domain.name_reading(ChosenReading(chosen=labels[0], alternatives=labels[1:]))


def _offered(parked: ParkedCall, counts: Mapping[str, int]) -> str:
    offered = "; ".join(
        f"{label} ({counts[label]} genes)" for label in card_labels(parked.tool_args)
    )
    return f"Readings offered: {offered}"


def _card_words(parked: ParkedCall | None, counts: Mapping[str, int]) -> str:
    if parked is None:
        return ""
    if hands_over(parked):
        return _offered(parked, counts)
    return f"approve {parked.tool_name}"


def explore_exchange(
    state: PipelineState,
    *,
    reply: str,
    parked: ParkedCall | None,
    answered: ParkedCall | None,
    counts: Mapping[str, int],
) -> Exchange:
    card = _card_words(parked, counts)
    if answered is None:
        return Exchange(said=state.user_prompt, reply=reply, card=card)
    if isinstance(answered, PendingDurableCall):
        return Exchange(kind="task_result", reply=reply, card=card)
    return Exchange(
        kind="card_answer",
        said=_answer_words(state, answered),
        reply=reply,
        card=card,
    )


def explore_state_delta(
    state: PipelineState,
    deps: LeadDeps,
    *,
    parked: ParkedCall | None,
    answered: ParkedCall | None,
    spent: SpendMeter,
    memories: list[MemoryValue],
) -> dict[str, Any]:
    delta: dict[str, Any] = {
        "domain": deps.state.domain,
        "retrieved_memories": memories,
        "turn_total_tokens": state.turn_total_tokens + spent.tokens,
        "turn_total_cost_usd": state.turn_total_cost_usd + spent.cost_usd,
    }
    if isinstance(parked, PendingDurableCall):
        delta["pending_durable_call"] = parked
    elif isinstance(answered, PendingDurableCall):
        delta["pending_durable_call"] = None
    if isinstance(parked, PendingApproval):
        delta["pending_approval"] = parked
    elif state.pending_approval is not None:
        delta["pending_approval"] = None
    return delta


__all__ = [
    "ExploreTurn",
    "explore_exchange",
    "explore_park",
    "explore_state_delta",
    "explore_turn_for",
    "hand_over_reading",
    "hands_over",
]
