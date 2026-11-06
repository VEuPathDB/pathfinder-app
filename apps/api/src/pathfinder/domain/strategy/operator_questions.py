from __future__ import annotations

from collections.abc import Sequence

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.clipped import clipped_text
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.operator_reading import PAIR
from pathfinder.domain.strategy.operator_reads import OperatorReading
from pathfinder.domain.strategy.question_options import (
    SetOperator,
    TypedOption,
    option_id,
)
from pathfinder.domain.strategy.questions import OpenQuestion

_LABEL_LIMIT = 120
_PAIRED: dict[CombineOp, str] = {
    CombineOp.INTERSECT: "{n}s in both {a} and {b}",
    CombineOp.UNION: "{n}s in {a} or {b}",
    CombineOp.MINUS: "{n}s in {a} but not in {b}",
    CombineOp.LONLY: "{n}s in {a} but not in {b}",
    CombineOp.RMINUS: "{n}s in {b} but not in {a}",
    CombineOp.RONLY: "{n}s in {b} but not in {a}",
    CombineOp.COLOCATE: "{n}s of {a} near {n}s of {b}",
}
_MANY: dict[CombineOp, str] = {
    CombineOp.INTERSECT: "{n}s in all of {listed}",
    CombineOp.UNION: "{n}s in any of {listed}",
}


def _listed(names: Sequence[str]) -> str:
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _finds(operator: CombineOp, names: Sequence[str], noun: str) -> str:
    if len(names) == PAIR:
        return _PAIRED[operator].format(n=noun, a=names[0], b=names[1])
    return _MANY[operator].format(n=noun, listed=_listed(names))


def _option(prefix: str, finds: str, binding: SetOperator) -> TypedOption:
    label = clipped_text(f"{prefix} {finds}", _LABEL_LIMIT)
    return TypedOption(id=option_id(label), label=label, binding=binding)


def _question(
    reading: OperatorReading, read: CombineOp, quotes: dict[str, str], noun: str
) -> OpenQuestion:
    names = [
        " and ".join(dict.fromkeys(f'"{quotes[rid]}"' for rid in ids if rid in quotes))
        for ids in reading.branches
    ]
    built, wanted = _finds(reading.built, names, noun), _finds(read, names, noun)
    return OpenQuestion(
        question=(
            f"Your words read as {wanted}, but the plan finds {built}. "
            f"Which should it find?"
        ),
        requirement_ids=[rid for ids in reading.branches for rid in ids],
        options=[
            _option(
                "Keep",
                built,
                SetOperator(criteria=reading.criteria, operator=reading.built),
            ),
            _option(
                "Change to",
                wanted,
                SetOperator(criteria=reading.criteria, operator=read),
            ),
        ],
    )


def operator_questions(
    spec: OperationalSpec, requirements: Sequence[Constraint], *, noun: str
) -> list[OpenQuestion]:
    quotes = {c.id: c.quote for c in requirements if c.quote}
    return [
        _question(reading, reading.read_operator, quotes, noun)
        for reading in spec.held_operator_reads()
        if reading.read == "disagrees"
        and reading.read_operator is not None
        and all(any(rid in quotes for rid in ids) for ids in reading.branches)
    ]
