from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic_ai import RunContext
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.held_answer import (
    Changed,
    Gaps,
    HeldAnswer,
    asked_gaps,
    gapped,
    held,
    with_question,
    without_question,
)
from strategist.ai.agents.state import AgentToolState
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.deltas import FrameResult, PassGap
from strategist.domain.refusal import Check, RefusalKey
from strategist.domain.strategy.card_answers import option_refusal
from strategist.domain.strategy.expression_handles import held_expressions, is_handle
from strategist.domain.strategy.question_options import SetValues
from strategist.domain.strategy.questions import SlotQuestion
from strategist.services.strategies.sheet_params import criterion_sheets


def unheld_handles(question: SlotQuestion, held: dict[str, str]) -> list[str]:
    if question.param_name != PHYLETIC_EXPRESSION_PARAM:
        return []
    offered = [*question.options, *(r.value for r in question.readings)]
    return [v.strip() for v in offered if is_handle(v) and v.strip() not in held]


def hold_an_option_to_a_held_expression(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    state = ctx.deps.agent_state
    held_names = held_expressions(state.built_expressions, state.operational_spec_draft)
    return [
        held(
            RefusalKey(
                check=Check.AN_OPTION_TO_A_HELD_EXPRESSION,
                criterion=question.criterion_id,
                parameter=question.param_name,
            ),
            (
                f"{question.criterion_id}.{question.param_name} offers {names}, and "
                "no expression of this conversation is held under that handle, so "
                "the card would bind nothing. Offer a handle "
                "build_phyletic_expression returned, or build the reading first."
            ),
            *_dropped(question, names),
        )
        for question in output.open_questions
        if (names := unheld_handles(question, held_names))
    ]


def _dropped(question: SlotQuestion, names: list[str]) -> tuple[Gaps, Changed]:
    gap = PassGap(
        kind="expression_handle_unknown",
        sentence=(
            f"The pass offered {names} on {question.criterion_id}."
            f"{question.param_name}, which no held expression answers, so the "
            "question was dropped."
        ),
    )
    return gapped(gap), lambda output: without_question(output, question)


def _refusals(
    question: SlotQuestion,
    state: AgentToolState,
    sheets: Mapping[str, Sequence[ParameterInfo]],
) -> list[str]:
    spec = state.operational_spec_draft
    criterion = next((c for c in spec.criteria if c.id == question.criterion_id), None)
    if criterion is not None and state.sets_the_site(
        criterion.search_name, question.param_name
    ):
        return []
    unheld = set(
        unheld_handles(question, held_expressions(state.built_expressions, spec))
    )
    return [
        why
        for wire in question.wires_offered(criterion)
        if wire.strip() not in unheld
        and (
            why := option_refusal(
                spec,
                SetValues(
                    criterion_id=question.criterion_id,
                    params={question.param_name: wire},
                ),
                sheets=sheets,
                expressions=state.built_expressions,
            )
        )
    ]


def _unbindable(question: SlotQuestion, refusals: list[str]) -> str:
    return (
        f"{question.criterion_id}.{question.param_name} offered a value the card "
        f"cannot bind: {'; '.join(refusals)}"
    )


def _free_text(question: SlotQuestion, said: str) -> tuple[Gaps, Changed]:
    gap = PassGap(
        kind="option_not_a_value",
        sentence=f"{said}, so the question asks in free text.",
    )
    return asked_gaps(question, gap), lambda output: with_question(
        output, question, options=[]
    )


async def hold_an_option_to_its_parameter(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    state = ctx.deps.agent_state
    asked = {q.criterion_id for q in output.open_questions}
    sheets = await criterion_sheets(
        ctx.deps.site_id,
        [c for c in state.operational_spec_draft.criteria if c.id in asked],
        state.infos_read_this_pass,
    )
    unbindable = [
        (question, _unbindable(question, refusals))
        for question in output.open_questions
        if (refusals := _refusals(question, state, sheets))
    ]
    return [
        held(
            RefusalKey(
                check=Check.AN_OPTION_TO_ITS_PARAMETER,
                criterion=question.criterion_id,
                parameter=question.param_name,
            ),
            (
                f"{said}. An option binds its value as written. Offer values this "
                "parameter takes, or ask in free text: leave `options` empty and "
                "the researcher answers in words."
            ),
            *_free_text(question, said),
        )
        for question, said in unbindable
    ]


__all__ = [
    "hold_an_option_to_a_held_expression",
    "hold_an_option_to_its_parameter",
    "unheld_handles",
]
