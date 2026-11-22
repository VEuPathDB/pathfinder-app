from __future__ import annotations

from pydantic_ai import DeferredToolRequests, RunContext

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.tools.standalone.graph_helpers import counted_noun
from strategist.domain.strategy.genome_questions import genome_reading_questions


def hold_the_genome_reading_to_a_question(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    match output:
        case FrameResult():
            pass
        case _:
            return output
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


__all__ = ["hold_the_genome_reading_to_a_question"]
