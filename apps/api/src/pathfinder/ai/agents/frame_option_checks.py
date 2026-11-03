from __future__ import annotations

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.card_answers import option_refusal
from pathfinder.domain.strategy.expression_handles import held_expressions, is_handle
from pathfinder.domain.strategy.question_options import SetValues
from pathfinder.domain.strategy.questions import SlotQuestion


def _unknown(question: SlotQuestion, held: dict[str, str]) -> list[str]:
    if question.param_name != PHYLETIC_EXPRESSION_PARAM:
        return []
    offered = [*question.options, *(r.value for r in question.readings)]
    return [v.strip() for v in offered if is_handle(v) and v.strip() not in held]


def hold_an_option_to_a_held_expression(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    if not isinstance(output, FrameResult):
        return output
    state = ctx.deps.agent_state
    held = held_expressions(state.built_expressions, state.operational_spec_draft)
    unknown = [
        (question, names)
        for question in output.open_questions
        if (names := _unknown(question, held))
    ]
    if not unknown:
        return output
    first, names = unknown[0]
    slot = f"{first.criterion_id}.{first.param_name}"
    if not may_refuse(ctx, state.refusals):
        dropped = [question for question, _ in unknown]
        return output.model_copy(
            update={
                "open_questions": [q for q in output.open_questions if q not in dropped]
            }
        ).with_gap(
            "expression_handle_unknown",
            f"The pass offered {names} on {slot}, which no held expression "
            "answers, so the question was dropped.",
        )
    state.refusals += 1
    msg = (
        f"{slot} offers {names}, and no expression of this conversation is held "
        "under that handle, so the card would bind nothing. Offer a handle "
        "build_phyletic_expression returned, or build the reading first."
    )
    raise ModelRetry(msg)


def _refusals(question: SlotQuestion, state: AgentToolState) -> list[str]:
    spec = state.operational_spec_draft
    criterion = next((c for c in spec.criteria if c.id == question.criterion_id), None)
    return [
        why
        for wire in question.wires_offered(criterion)
        if (
            why := option_refusal(
                spec,
                SetValues(
                    criterion_id=question.criterion_id,
                    params={question.param_name: wire},
                ),
                sheets={},
                expressions=state.built_expressions,
            )
        )
    ]


def _unbindable(question: SlotQuestion, refusals: list[str]) -> str:
    return (
        f"{question.criterion_id}.{question.param_name} offered a value the card "
        f"cannot bind: {'; '.join(refusals)}"
    )


def hold_an_option_to_its_parameter(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    if not isinstance(output, FrameResult):
        return output
    state = ctx.deps.agent_state
    held = [(q, _refusals(q, state)) for q in output.open_questions]
    refused = [_unbindable(q, refusals) for q, refusals in held if refusals]
    if not refused:
        return output
    if may_refuse(ctx, state.refusals):
        state.refusals += 1
        msg = (
            f"{'. '.join(refused)}. An option binds its value as written. Offer "
            "values this parameter takes, or ask in free text: leave `options` empty "
            "and the researcher answers in words."
        )
        raise ModelRetry(msg)
    return output.model_copy(
        update={
            "open_questions": [
                q.model_copy(update={"options": []}) if refusals else q
                for q, refusals in held
            ]
        }
    ).with_gaps(
        [
            PassGap(
                kind="option_not_a_value",
                sentence=f"{said}, so the question asks in free text.",
            )
            for said in refused
        ]
    )


__all__ = ["hold_an_option_to_a_held_expression", "hold_an_option_to_its_parameter"]
