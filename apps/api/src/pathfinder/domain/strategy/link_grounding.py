from __future__ import annotations

import math
from typing import NamedTuple

from veupathdb.domain.parameters import to_wire

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
    CountValue,
    GroundedConstraint,
    OrthologValue,
    PropertyValue,
    TextValue,
)
from pathfinder.domain.strategy.linked_values import (
    NO_LINK,
    linked_params,
    linking,
    not_verified,
    untyped,
)
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.organism_scope import selected_organisms
from pathfinder.domain.strategy.realized_spec import RealizedSpec
from pathfinder.domain.strategy.step_naming import criterion_title
from pathfinder.domain.strategy.words import words_of

_SYNTENIC = "isSyntenic"
_NO_STEP = "no step of the strategy states it"
_NO_NUMBER = "no linked parameter or step count holds a number to compare"
_UNITS_UNSTATED = (
    "each differs from the stated number by a power of ten and nothing typed states "
    "their units"
)


def _bounds_alike(asked: CountValue, number: float) -> bool:
    match asked.op:
        case ">":
            beside = asked.value + 1
        case "<":
            beside = asked.value - 1
        case _:
            beside = asked.value
    whole = asked.value.is_integer()
    return math.isclose(number, asked.value) or (whole and math.isclose(number, beside))


def _another_scale(asked: CountValue, number: float) -> bool:
    if asked.value <= 0 or number <= 0:
        return False
    exponent = math.log10(number / asked.value)
    return math.isclose(exponent, round(exponent))


def _met(c: Constraint, param: str, value: str) -> GroundedConstraint:
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        realized_value=value,
        realized_param=param,
    )


def _missed(c: Constraint, param: str, value: str, note: str) -> GroundedConstraint:
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.SUBSTITUTED,
        realized_value=value,
        realized_param=param,
        note=note,
    )


class _CountReading(NamedTuple):
    param: str
    shown: str
    met: bool
    said: str
    number: float


def _count_readings(
    c: Constraint, asked: CountValue, realized: RealizedSpec
) -> list[_CountReading]:
    params = [
        _CountReading(
            p.name, p.wire, _bounds_alike(asked, n), f"{p.name} holds {p.wire}", n
        )
        for p in linked_params(c, realized.criteria)
        if (n := p.number) is not None
    ]
    counts = [
        _CountReading("", str(n), asked.holds(n), f"the step returns {n}", n)
        for k in realized.criteria
        for link in k.answers
        if link.requirement == c.id and link.result_size
        if (n := k.result_count) is not None
    ]
    return [*params, *counts]


def ground_count(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    match c.value:
        case CountValue() as asked:
            pass
        case _:
            return untyped(c)
    readings = _count_readings(c, asked, realized)
    if not readings:
        return not_verified(c, "no_value_to_compare", _NO_NUMBER)
    unmet = [r for r in readings if not r.met]
    if not unmet:
        return _met(c, readings[0].param, readings[0].shown)
    off = next(
        (r for r in unmet if not (r.param and _another_scale(asked, r.number))), None
    )
    if off is not None:
        return _missed(c, off.param, off.shown, f"asked {asked.shown}, {off.said}")
    said = ", ".join(r.said for r in unmet)
    note = f"asked {asked.shown}, {said}: {_UNITS_UNSTATED}"
    return not_verified(c, "no_value_to_compare", note)


def ground_ortholog(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    match c.value:
        case OrthologValue() as asked:
            pass
        case _:
            return untyped(c)
    linked = linking(c, realized.criteria)
    if not linked:
        return not_verified(c, "no_step_states_it", _NO_STEP)
    targets = {
        organism
        for k in linked
        if k.role == "transform"
        for organism in selected_organisms(k)
    }
    if not targets:
        return not_verified(
            c,
            "no_value_to_compare",
            "no ortholog step that answers it targets an organism",
        )
    shown = ", ".join(sorted(targets))
    if targets != set(asked.organisms):
        note = f"asked orthologs in {', '.join(asked.organisms)}, the transform targets {shown}"
        return _missed(c, "", shown, note)
    if asked.syntenic is None:
        return _met(c, "", shown)
    return _synteny(c, linked, shown, syntenic=asked.syntenic)


def _synteny(
    c: Constraint, linked: list[Criterion], shown: str, *, syntenic: bool
) -> GroundedConstraint:
    settings = [
        to_wire(k.resolved_params[_SYNTENIC].value)
        for k in linked
        if k.role == "transform" and _SYNTENIC in k.resolved_params
    ]
    if not settings:
        return not_verified(
            c,
            "no_value_to_compare",
            f"no ortholog step that answers it sets {_SYNTENIC}",
        )
    wanted = "yes" if syntenic else "no"
    off = next((s for s in settings if s != wanted), None)
    if off is None:
        return _met(c, "", shown)
    asked = (
        "asked syntenic orthologs"
        if syntenic
        else "asked orthologs not limited to syntenic ones"
    )
    return _missed(c, _SYNTENIC, off, f"{asked}, {_SYNTENIC} holds '{off}'")


def _states(asked: TextValue, bound: str) -> bool:
    if asked.exact:
        return bound.strip().strip('"').casefold() == asked.phrase.casefold()
    return set(words_of(asked.phrase)) <= set(words_of(bound))


def ground_text(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    match c.value:
        case TextValue() as asked:
            pass
        case _:
            return untyped(c)
    if not linking(c, realized.criteria):
        return not_verified(c, "no_step_states_it", _NO_STEP)
    params = linked_params(c, realized.criteria)
    if not params:
        return not_verified(c, "no_value_to_compare", NO_LINK)
    off = next((p for p in params if not _states(asked, p.wire)), None)
    if off is not None:
        how = "the phrase" if asked.exact else "every word of"
        note = f"asked {how} '{asked.phrase}', {off.name} holds '{off.wire}'"
        return _missed(c, off.name, off.wire, note)
    return _met(c, params[0].name, params[0].wire)


def ground_property(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    match c.value:
        case PropertyValue():
            pass
        case _:
            return untyped(c)
    linked = linking(c, realized.criteria)
    if not linked:
        return not_verified(c, "no_step_states_it", _NO_STEP)
    title = criterion_title(linked[0]).head
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        realized_value=title,
        note=f"answered by step '{title}'",
    )
