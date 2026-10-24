"""How a card names the value an option binds: its term, its label and the
count the site returned at it."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PhyleticTree,
    to_wire,
)

from pathfinder.domain.log2_scale import fold_label, on_scale, scale_of
from pathfinder.domain.strategy.expression_handles import (
    expression_reading,
    is_handle,
    shown_wire,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec

_NO_READINGS: Mapping[str, str] = MappingProxyType({})


def value_readings(criterion: Criterion | None, param: str, value: str) -> list[str]:
    """The values an offered value binds. A positive number offered for a
    parameter on the log2 scale is read as a fold and as a log2 value, since
    the researcher may mean either."""
    display = "" if criterion is None else criterion.display_name_of(param)
    if scale_of(display) != "log2":
        return [value]
    try:
        number = float(value)
    except ValueError:
        return [value]
    if number <= 0:
        return [value]
    return list(dict.fromkeys([f"{on_scale(number, 'fold', 'log2'):g}", value]))


def value_reading(
    criterion: Criterion,
    param: str,
    term: str,
    readings: Mapping[str, str] = _NO_READINGS,
) -> str:
    """The label the site gave for a vocabulary term, else the term."""
    shown = shown_wire(param, term)
    labelled = next(
        (
            m.label
            for m in criterion.measurements
            if m.kind == "vocabulary_label"
            and m.param == param
            and m.reading in (term, shown)
        ),
        None,
    )
    if labelled is not None:
        return labelled
    if shown in readings:
        return readings[shown]
    if param == PHYLETIC_EXPRESSION_PARAM and not is_handle(term):
        return expression_reading(term, PhyleticTree())
    return shown


def term_of(criterion: Criterion | None, param: str, value: str) -> str:
    """The vocabulary term an offered value names: a label the site gave for a
    term of the parameter names that term, and any other value is the term."""
    if criterion is None:
        return value
    return next(
        (
            m.reading
            for m in criterion.measurements
            if m.kind == "vocabulary_label" and m.param == param and m.label == value
        ),
        value,
    )


def option_label(
    criterion: Criterion | None,
    param: str,
    value: str,
    *,
    noun: str,
    readings: Mapping[str, str] = _NO_READINGS,
) -> str:
    """The value an option binds, named by its parameter, with its count.

    A parameter the site named for the criterion leads the value, a value on
    the log2 scale is followed by the fold it stands for, and a count the site
    returned at that value follows it, in ``noun``.
    """
    if criterion is None:
        return value
    named = criterion.param_display_names.get(param, "")
    shown = value_reading(criterion, param, value, readings)
    fold = fold_label(named, value)
    if fold:
        shown = f"{shown} ({fold})"
    label = f"{named} {shown}" if named else shown
    return with_count(label, count_at(criterion, param, value), noun)


def with_count(label: str, count: int | None, noun: str) -> str:
    if count is None:
        return label
    return f"{label}: {count} {noun}" if count == 1 else f"{label}: {count} {noun}s"


def count_at(criterion: Criterion | None, param: str, value: str) -> int | None:
    """The count the site returned with the parameter at this wire value.

    The criterion's own count is measured at the value it binds; a measurement
    is measured at the reading it records.
    """
    if criterion is None:
        return None
    held = criterion.resolved_params.get(param)
    if held is not None and to_wire(held.value) == value:
        return criterion.result_count
    return next(
        (
            m.count
            for m in criterion.measurements
            if m.param == param
            and m.reading in (value, shown_wire(param, value))
            and m.count is not None
        ),
        None,
    )


def with_readings(
    spec: OperationalSpec | None, readings: Mapping[str, str]
) -> OperationalSpec | None:
    if spec is None:
        return None
    criteria = []
    for criterion in spec.criteria:
        held = criterion.resolved_params.get(PHYLETIC_EXPRESSION_PARAM)
        if held is None:
            criteria.append(criterion)
            continue
        reading = value_reading(
            criterion, PHYLETIC_EXPRESSION_PARAM, to_wire(held.value), readings
        )
        bound = {
            **criterion.resolved_params,
            PHYLETIC_EXPRESSION_PARAM: held.model_copy(update={"label": reading}),
        }
        criteria.append(criterion.model_copy(update={"resolved_params": bound}))
    return spec.model_copy(update={"criteria": criteria})
