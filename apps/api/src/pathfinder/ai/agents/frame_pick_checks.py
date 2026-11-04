from __future__ import annotations

from pydantic_ai import DeferredToolRequests, RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.strategy.genome_questions import genome_reading_questions
from pathfinder.domain.strategy.vocab_picks import (
    spec_held_open,
    unsettled_questions,
)


def _hold_the_genome_reading_to_a_question(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> FrameResult:
    draft = ctx.deps.agent_state.operational_spec_draft
    asked = genome_reading_questions(draft, noun=counted_noun(draft.record_type))
    if not asked:
        return output
    return output.model_copy(
        update={
            "disposition": "needs_user",
            "open_questions": [*output.open_questions, *asked],
        }
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
    if held != draft:
        asked = unsettled_questions(draft.criteria, picks, output.open_questions)
        state.operational_spec_draft = held
        output = output.model_copy(
            update={
                "disposition": "needs_user",
                "open_questions": [*output.open_questions, *asked],
            }
        )
    return _hold_the_genome_reading_to_a_question(ctx, output)


__all__ = ["hold_an_unsettled_pick_to_a_question"]
