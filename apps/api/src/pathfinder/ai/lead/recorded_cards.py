from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from assistant_core.conversation.vercel_adapter import DeferredToolHint
from assistant_core.graph.turn_state import ConsultOption, UserQuestionAnswer
from pydantic import ConfigDict, Field
from veupathdb.model import CamelModel

from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.domain.strategy.question_options import (
    Keep,
    SetValues,
    TypedOption,
    Withdraw,
)
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.domain.strategy.readings import ReadValues

_CONSULT = "consult_user"


def _recommends(question: OpenQuestion, option: TypedOption) -> bool:
    match option.binding:
        case ReadValues(params=params, reading=reading):
            return question.recommended_value in (reading, *params.values())
        case SetValues(params=params):
            return question.recommended_value in params.values()
        case _:
            return option.label == question.recommended_value


def _asks_about(question: OpenQuestion) -> str:
    keys: list[str] = []
    for option in question.options:
        match option.binding:
            case ReadValues(replaces=replaced):
                keys.extend(replaced)
            case Withdraw(constraint_id=key) | Keep(constraint_id=key):
                keys.append(key)
            case _:
                continue
    return keys[0] if keys else ""


def _slots_asked(question: OpenQuestion) -> set[str]:
    slots: set[str] = set()
    for option in question.options:
        match option.binding:
            case (
                SetValues(criterion_id=criterion, params=params)
                | ReadValues(criterion_id=criterion, params=params)
            ):
                slots |= {criterion, *params, *(f"{criterion}.{p}" for p in params)}
            case _:
                continue
    return slots


def card_questions(questions: Sequence[OpenQuestion]) -> list[CardQuestion]:
    """The recorded questions as the card asks them, each option by its label."""
    return [
        CardQuestion(
            id=f"q{index}",
            prompt=question.question,
            dimension=question.dimension,
            requirement=_asks_about(question),
            options=[
                ConsultOption(label=o.label, recommended=_recommends(question, o))
                for o in question.options
            ],
        )
        for index, question in enumerate(questions, 1)
    ]


def the_card_asked(
    written: Sequence[CardQuestion], recorded: Sequence[OpenQuestion]
) -> list[CardQuestion]:
    offered = [q for q in recorded if q.options]
    held = card_questions(offered)
    prompts = {q.prompt for q in held}
    asked_about = {q.requirement for q in held} - {""}
    asked_about |= {slot for q in offered for slot in _slots_asked(q)}
    ids = {q.id for q in held}
    own = [
        q
        for q in written
        if q.prompt not in prompts and q.requirement not in asked_about
    ]
    return [
        *held,
        *(
            q if q.id not in ids else q.model_copy(update={"id": f"own-{n}"})
            for n, q in enumerate(own, 1)
        ),
    ]


def answered_on_the_card(
    answers: Sequence[UserQuestionAnswer], shown: Sequence[CardQuestion]
) -> list[UserQuestionAnswer]:
    prompts = {q.id: q.prompt for q in shown}
    return [
        a.model_copy(update={"prompt": prompts[a.question_id]})
        if a.question_id in prompts
        else a
        for a in answers
    ]


class _ConsultCall(CamelModel):
    model_config = ConfigDict(extra="allow")

    questions: list[CardQuestion] = Field(default_factory=list)


def completed_consult_input(
    written: object, recorded: Sequence[OpenQuestion]
) -> dict[str, object]:
    call = _ConsultCall.model_validate(written)
    asked = call.model_copy(
        update={"questions": the_card_asked(call.questions, recorded)}
    )
    return asked.model_dump(by_alias=True, mode="json")


def completed_hint(
    hint: DeferredToolHint, recorded: Sequence[OpenQuestion]
) -> DeferredToolHint:
    if hint.tool_name != _CONSULT:
        return hint
    return replace(hint, tool_args=completed_consult_input(hint.tool_args, recorded))
