from __future__ import annotations

from collections.abc import Sequence

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.requirement_reports import RequirementProblem
from pathfinder.domain.strategy.step_rationale import SearchRationale

_GAP = "question_without_readings"


def _in_words(question: SlotQuestion) -> tuple[str, PassGap]:
    asked = question.question
    if not question.names_a_slot:
        return (
            (
                f"{asked!r} offers {question.options} and names no `criterion_id` "
                "and `param_name`, so no option binds a value: record the criterion "
                "the choice sets with set_criterion and null for that parameter, "
                "name both in the question, and offer the choices as its readings"
            ),
            PassGap(
                kind=_GAP,
                sentence=f"{asked!r} offers its choices on no slot, so the card "
                "asks it in words.",
            ),
        )
    slot = f"{question.criterion_id}.{question.param_name}"
    return (
        (
            f"{asked!r} asks for {slot} in words: offer two or three `readings` of "
            f"it, each a `label`, the `value` {question.param_name} takes as the "
            "site builds it, and a `caveat`"
        ),
        PassGap(
            kind=_GAP,
            sentence=f"{asked!r} asks for {slot} in words, with no reading the "
            "site builds.",
        ),
    )


def _left_open(key: str) -> tuple[str, PassGap]:
    return (
        (
            f"{key} is reported request_leaves_it_open and no question asks for it: "
            f"name {key} in the `requirements` of the question that asks for its "
            "value, which names the `criterion_id` and `param_name` it sets and "
            "offers two or three `readings` when that parameter takes readings; "
            "keep the criterion with set_criterion and null for that parameter "
            "when the draft does not hold it"
        ),
        PassGap(
            kind=_GAP,
            sentence=f"The pass leaves {key} open and asks no question for it.",
        ),
    )


def _left_open_by_its_reason(criterion: Criterion) -> list[str]:
    match criterion.rationale:
        case SearchRationale(basis="parameter", term=term):
            return [
                s.param_name
                for s in criterion.open_params
                if term in (s.param_name, criterion.display_name_of(s.param_name))
            ]
        case _:
            return []


def _stated_left_open(output: FrameResult, criteria: Sequence[Criterion]) -> list[str]:
    open_keys = {
        r.requirement
        for r in output.requirement_problems
        if r.problem is RequirementProblem.REQUEST_LEAVES_IT_OPEN
    }
    asked = {
        (q.criterion_id, q.param_name)
        for q in output.open_questions
        if set(q.requirements) <= open_keys
    }
    return [
        f"{c.id}.{param}"
        for c in criteria
        for param in _left_open_by_its_reason(c)
        if (c.id, param) not in asked
    ]


def _unasked_slot(slot: str) -> tuple[str, PassGap]:
    return (
        (
            f"{slot} is left open as the reason its search was chosen, and no "
            "question asks for it: bind the value the request states, or ask for "
            "it with readings in a question that names the slot and, in "
            "`requirements`, only keys reported request_leaves_it_open; with no "
            "requirement list, the question names no key"
        ),
        PassGap(
            kind=_GAP,
            sentence=f"{slot} is left open with no requirement reported open for it.",
        ),
    )


def hold_a_choice_to_its_readings(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    if not isinstance(output, FrameResult):
        return output
    state = ctx.deps.agent_state
    draft = state.operational_spec_draft
    by_id = {c.id: c for c in draft.criteria}
    held = [
        *(
            _in_words(q)
            for q in output.open_questions
            if q.asks_a_value_in_words(by_id.get(q.criterion_id))
        ),
        *(_left_open(key) for key in output.left_open_without_a_choice(draft)),
        *(_unasked_slot(slot) for slot in _stated_left_open(output, draft.criteria)),
    ]
    if not held:
        return output
    if not may_refuse(ctx, state.refusals):
        return output.with_gaps([gap for _, gap in held])
    state.refusals += 1
    msg = (
        f"A question about a value the site builds offers what the site builds: "
        f"{'; '.join(problem for problem, _ in held)}. The Lead counts each "
        f"reading on the site before the card shows it."
    )
    raise ModelRetry(msg)
