"""How a card names the value an option binds: its term, its label and the
count the site returned at it."""

from __future__ import annotations

from veupathdb.domain.parameters import to_wire

from pathfinder.domain.log2_scale import fold_label, on_scale, scale_of
from pathfinder.domain.strategy.operational_spec import Criterion


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


def _label_of(criterion: Criterion, param: str, term: str) -> str:
    """The label the site gave for a vocabulary term, else the term."""
    return next(
        (
            m.label
            for m in criterion.measurements
            if m.kind == "vocabulary_label" and m.param == param and m.reading == term
        ),
        term,
    )


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
    criterion: Criterion | None, param: str, value: str, *, noun: str
) -> str:
    """The value an option binds, named by its parameter, with its count.

    A parameter the site named for the criterion leads the value, a value on
    the log2 scale is followed by the fold it stands for, and a count the site
    returned at that value follows it, in ``noun``.
    """
    if criterion is None:
        return value
    named = criterion.param_display_names.get(param, "")
    shown = _label_of(criterion, param, value)
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
            if m.param == param and m.reading == value and m.count is not None
        ),
        None,
    )
