from __future__ import annotations

from collections.abc import Sequence

from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb.errors import ValidationError

from strategist.domain.strategy.card_answers import option_value
from strategist.domain.strategy.expression_handles import shown_wire, stated_text
from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec
from strategist.domain.strategy.question_options import SetValues, TypedOption
from strategist.domain.strategy.questions import OpenQuestion
from strategist.domain.strategy.readings import ReadValues


def _as_offered(name: str, value: str | list[str]) -> str:
    match value:
        case str():
            return shown_wire(name, value)
        case _:
            return ", ".join(value)


def _set_to(criterion: Criterion | None, name: str, value: str | list[str]) -> str:
    if criterion is None:
        return _as_offered(name, value)
    try:
        return stated_text(name, option_value(criterion, name, value))
    except ValidationError:
        return _as_offered(name, value)


def _chosen(
    label: str, question: OpenQuestion | None, spec: OperationalSpec | None
) -> str:
    options = question.options if question is not None else []
    option = next((o for o in options if o.label == label), None)
    match option:
        case TypedOption(
            binding=SetValues(criterion_id=cid, params=params)
            | ReadValues(criterion_id=cid, params=params)
        ):
            criteria = [] if spec is None else spec.criteria
            criterion = next((c for c in criteria if c.id == cid), None)
            sets = ", ".join(
                f"{name} to {_set_to(criterion, name, value)}"
                for name, value in params.items()
            )
            return f"{label} (sets {sets})"
        case _:
            return label


def answers_text(
    answers: list[UserQuestionAnswer],
    questions: Sequence[OpenQuestion],
    spec: OperationalSpec | None,
) -> str:
    recorded = {q.question: q for q in questions}
    parts: list[str] = []
    for a in answers:
        question = recorded.get(a.prompt)
        chosen = (
            ", ".join(_chosen(label, question, spec) for label in a.chosen_labels)
            if a.chosen_labels
            else "(free text)"
        )
        line = f'"{a.prompt}" -> {chosen}'
        if a.note:
            line += f" - note: {a.note}"
        parts.append(line)
    return "; ".join(parts)


__all__ = ["answers_text"]
