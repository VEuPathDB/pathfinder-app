from __future__ import annotations

from pydantic_ai import DeferredToolRequests, RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.vocab_picks import (
    spec_held_open,
    unsettled_questions,
)


def hold_an_unsettled_pick_to_a_question(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    match output:
        case FrameResult():
            pass
        case _:
            return output
    state = ctx.deps.agent_state
    draft = state.operational_spec_draft
    picks = list(state.vocab_picks.values())
    held = spec_held_open(draft, picks)
    if held == draft:
        return output
    asked = unsettled_questions(draft.criteria, picks, output.open_questions)
    state.operational_spec_draft = held
    return output.model_copy(
        update={
            "disposition": "needs_user",
            "open_questions": [*output.open_questions, *asked],
        }
    )


__all__ = ["hold_an_unsettled_pick_to_a_question"]
