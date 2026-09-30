"""The measurements a criterion holds, each as the clause a reader is shown."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, ParamValue

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    Measurement,
    ValueSource,
    plain_value,
)

_SET_BY: dict[ValueSource, str] = {
    "default": "the site's default of",
    "chosen": "the chosen",
    "stated": "the stated",
    "card": "the answered",
    "held": "the strategy's",
}


_NOT_MEASURED = "not measured"
# A pick of more values than this is named by its size: the row shows it whole.
_NAMED_WHOLE = 3


def shown_value(value: ParamValue) -> str:
    """The value as a clause or a caveat names it."""
    match value:
        case MultiPickValue(values=picks) if len(picks) > _NAMED_WHOLE:
            return f"{len(picks)} values"
        case _:
            return plain_value(value)


def _records(count: int | None, noun: str) -> str:
    if count is None:
        return _NOT_MEASURED
    return f"{count:,} {noun}" if count == 1 else f"{count:,} {noun}s"


def _other(count: int | None) -> str:
    return _NOT_MEASURED if count is None else f"{count:,}"


def _counted(
    criterion: Criterion, m: Measurement, at: str, other: str, noun: str
) -> str:
    """The count at the bound value, then the count at the other reading."""
    name = criterion.display_name_of(m.param)
    if criterion.result_count is None:
        return f"{name} {other}: {_records(m.count, noun)}"
    counted = _records(criterion.result_count, noun)
    return f"{name} {at}: {counted}; {other}: {_other(m.count)}"


def _worded(criterion: Criterion, m: Measurement, noun: str) -> str | None:
    """The clause of a measurement that holds words, not another count."""
    bound = criterion.resolved_params[m.param]
    name = criterion.display_name_of(m.param)
    match m.kind:
        case "bound_count" if m.count is not None:
            return (
                f"{name} at {_SET_BY[bound.source]} {shown_value(bound.value)}: "
                f"{_records(m.count, noun)}; its other readings: {_NOT_MEASURED}"
            )
        case "bound_count":
            return f"{name} at {_SET_BY[bound.source]} {shown_value(bound.value)}: {_NOT_MEASURED}"
        case "options_not_taken":
            taken = ", ".join(m.unchosen) or f"{m.unchosen_count:,} options"
            return f"{name} did not take {taken}"
        case "not_measurable":
            return f"{name}: not measurable, {m.reading}"
        case "vocabulary_label":
            return f"{name} {m.reading} is labelled {m.label!r}"
        case _:
            return None


def _cut(criterion: Criterion, m: Measurement) -> str | None:
    """The clause of a pick taken from a read: a list that showed part of what
    matched, a lookup, or a picked label that holds no word of the lookup."""
    name = criterion.display_name_of(m.param)
    matching = f"that match {m.reading}" if m.reading else "of its vocabulary"
    taken = m.count or 0
    of_the = f"{name} took {taken:,} of the {taken + m.unchosen_count:,} entries"
    match m.kind:
        case "picked_from_a_cut_list":
            return (
                f"{of_the} {matching}; the list it was picked from showed only "
                f"part of them"
            )
        case "picked_from_a_lookup":
            return f"{of_the} {matching}"
        case "label_without_the_concept":
            return f"{name} took {m.label!r}, whose label holds no word of {m.reading}"
        case _:
            return None


# The other reading of a value counted as it is written, by measurement kind.
_AS_VALUE_READINGS = {
    "wildcard_phrase": "as {}",
    "site_default": "at the site's default, {}",
}


def _clause(criterion: Criterion, m: Measurement, noun: str) -> str:
    worded = _worded(criterion, m, noun) or _cut(criterion, m)
    if worded is not None:
        return worded
    bound = criterion.resolved_params[m.param]
    name = criterion.display_name_of(m.param)
    value = shown_value(bound.value)
    match m.kind:
        case "loosest_bound":
            at = f"at {_SET_BY[bound.source]} {value}"
            return _counted(criterion, m, at, f"at {m.reading}", noun)
        case "wildcard_phrase" | "site_default":
            other = _AS_VALUE_READINGS[m.kind].format(m.reading)
            return _counted(criterion, m, f"as {value}", other, noun)
        case "site_search_reach":
            return f"the site search finds {_records(m.count, noun)} for {m.reading}"
        case _:
            return f"{name} with an ortholog in {m.reading}: {_records(m.count, noun)}"


def measurement_clauses(criterion: Criterion, *, noun: str) -> list[str]:
    """One clause per measurement of a value the criterion still binds, its
    counts in ``noun``."""
    return [
        _clause(criterion, m, noun)
        for m in criterion.measurements
        if m.param in criterion.resolved_params
    ]


# The kinds of a pick taken from a vocabulary read, shown whoever set the value.
_TAKEN_FROM_A_READ = frozenset({"picked_from_a_cut_list", "picked_from_a_lookup"})
# The label is the row's label, and a label gap is a caveat of its own.
_SHOWN_ELSEWHERE = frozenset({"vocabulary_label", "label_without_the_concept"})


def read_pick_clauses(criterion: Criterion, param: str, *, noun: str) -> list[str]:
    """The clause of a pick taken from a vocabulary read, whoever set the value."""
    if param not in criterion.resolved_params:
        return []
    return [
        _clause(criterion, m, noun)
        for m in criterion.measurements
        if m.param == param and m.kind in _TAKEN_FROM_A_READ
    ]


def counted_clauses(criterion: Criterion, param: str, *, noun: str) -> list[str]:
    """The clauses of the counted measurements of one value the criterion binds.

    A value a count measures is never shown as not measurable.
    """
    if param not in criterion.resolved_params:
        return []
    held = [m for m in criterion.measurements if m.param == param]
    counted = any(m.count is not None for m in held)
    return [
        _clause(criterion, m, noun)
        for m in held
        if m.kind not in _SHOWN_ELSEWHERE
        and not (counted and m.kind == "not_measurable")
    ]
