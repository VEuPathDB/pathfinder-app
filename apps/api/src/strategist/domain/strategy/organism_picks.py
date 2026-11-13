from __future__ import annotations

from collections.abc import Sequence

from pydantic import ConfigDict, Field
from veupathdb.model import CamelModel

from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.question_options import (
    SetOrganism,
    TypedOption,
    option_id,
)
from strategist.domain.strategy.questions import OpenQuestion

_OFFERED = 5


class OrganismPick(CamelModel):
    model_config = ConfigDict(frozen=True)

    quote: str = Field(min_length=1)
    picked: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    offered: list[str] = Field(default_factory=list, max_length=_OFFERED)


def unnamed_organisms(requirements: Sequence[Constraint]) -> list[Constraint]:
    return [
        c
        for c in requirements
        if c.kind is ConstraintKind.ORGANISM
        and c.organism is None
        and c.source is ConstraintSource.USER_EXPLICIT
    ]


def _option(requirement: Constraint, entry: str) -> TypedOption:
    return TypedOption(
        id=option_id(entry),
        label=entry,
        binding=SetOrganism(constraint_id=requirement.id, organism=entry),
    )


def _question(requirement: Constraint, pick: OrganismPick) -> OpenQuestion:
    offered = pick.offered if len(pick.offered) > 1 else []
    return OpenQuestion(
        question=f'Which organism of this site do you mean by "{pick.quote}"?',
        dimension=ConstraintKind.ORGANISM,
        recommended_value=pick.picked or "",
        requirement_ids=[requirement.id],
        options=[_option(requirement, entry) for entry in offered],
    )


def asked_organisms(
    requirements: Sequence[Constraint], picks: Sequence[OrganismPick]
) -> list[tuple[Constraint, OrganismPick]]:
    by_quote = {pick.quote: pick for pick in picks}
    return [
        (c, by_quote[c.quote])
        for c in unnamed_organisms(requirements)
        if c.quote in by_quote
    ]


def organism_questions(
    requirements: Sequence[Constraint], picks: Sequence[OrganismPick]
) -> list[OpenQuestion]:
    return [_question(c, pick) for c, pick in asked_organisms(requirements, picks)]


def _names_an_organism(option: TypedOption) -> bool:
    match option.binding:
        case SetOrganism():
            return True
        case _:
            return False


def asks_an_organism(questions: Sequence[OpenQuestion]) -> bool:
    return any(_names_an_organism(o) for q in questions for o in q.options)


__all__ = [
    "OrganismPick",
    "asked_organisms",
    "asks_an_organism",
    "organism_questions",
    "unnamed_organisms",
]
