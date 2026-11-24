from __future__ import annotations

from functools import reduce

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext

from strategist.ai.agents.frame_expression_checks import hold_the_taxa_to_their_scope
from strategist.ai.agents.frame_genome_checks import (
    hold_the_genome_reading_to_a_question,
)
from strategist.ai.agents.frame_option_checks import (
    hold_an_option_to_a_held_expression,
    hold_an_option_to_its_parameter,
)
from strategist.ai.agents.frame_reading_checks import hold_the_readings_to_the_site
from strategist.ai.agents.frame_result_checks import (
    hold_an_absence_to_a_read,
    hold_an_organism_to_a_step,
    hold_the_questions_to_a_dimension,
    hold_the_questions_to_the_draft,
    hold_the_reports_to_the_refusals,
    hold_the_reports_to_the_requirement_list,
    hold_the_route_to_another_site,
    hold_the_structure_to_bound_criteria,
)
from strategist.ai.agents.held_answer import Changed, HeldAnswer
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.deltas import FrameResult, PassGap
from strategist.domain.refusal import Problems
from strategist.platform.refusals import ANSWER_REFUSALS_PER_KEY, last_answer

_HELD_FIRST = (
    hold_the_reports_to_the_requirement_list,
    hold_an_absence_to_a_read,
    hold_an_organism_to_a_step,
    hold_the_questions_to_a_dimension,
    hold_the_questions_to_the_draft,
    hold_the_structure_to_bound_criteria,
    hold_the_route_to_another_site,
    hold_the_reports_to_the_refusals,
    hold_an_option_to_a_held_expression,
)


async def _held(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> tuple[Changed, list[HeldAnswer]]:
    spell, read = await hold_the_readings_to_the_site(ctx, output)
    return spell, [
        *(answer for check in _HELD_FIRST for answer in check(ctx, output)),
        *await hold_an_option_to_its_parameter(ctx, output),
        *read,
        *await hold_the_taxa_to_their_scope(ctx, output),
    ]


async def hold_the_frame_answer(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    match output:
        case FrameResult():
            pass
        case _:
            return output
    spell, held = await _held(ctx, output)
    state = ctx.deps.agent_state
    if not last_answer(ctx):
        found = Problems(found=tuple(answer.problem for answer in held))
        charge = state.answer_ledger.charge(found, ANSWER_REFUSALS_PER_KEY)
        state.answer_ledger = charge.ledger
        if not charge.refused.empty:
            raise ModelRetry(charge.refused.text())
    answered = spell(
        reduce(lambda changed, answer: answer.let_through(changed), held, output)
    )
    spent = [
        PassGap(kind="refusal_spent", sentence=refusal.note)
        for refusal in ctx.deps.refusal_book.spent_in(ctx.run_id or "")
    ]
    gaps = [gap for answer in held for gap in answer.gaps(answered)]
    return hold_the_genome_reading_to_a_question(
        ctx, answered.with_gaps([*gaps, *spent])
    )


__all__ = ["hold_the_frame_answer"]
