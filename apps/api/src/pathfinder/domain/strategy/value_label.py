"""The label the parameter sheet gives a bound value: the vocabulary display of
a pick, the field display of a filter clause, or the organism a species code
names in the clade tree."""

from __future__ import annotations

from collections.abc import Sequence

from veupathdb.domain.parameters import (
    PHYLETIC_PARAM_NAMES,
    FilterValue,
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    match_exact_option,
    read_census,
    to_wire,
)
from veupathdb_mcp.catalog import ParameterInfo

# A vocabulary label writes its segments apart with this separator.
_SEGMENT = " : "
# The literal the site writes for an empty species list.
_NO_SPECIES = "n/a"
_JOIN = ", "


def species_codes(value: ParamValue) -> list[str]:
    """The species codes a phyletic list or a census pattern names."""
    wire = to_wire(value)
    states = read_census(wire).states
    if states is not None:
        return list(states)
    return [
        code
        for part in wire.split(",")
        if (code := part.strip()) and code.casefold() != _NO_SPECIES
    ]


def _tree_labels(
    value: ParamValue, sheet: Sequence[ParameterInfo]
) -> list[tuple[str, str]]:
    tree = next(
        (
            i.vocabulary()
            for i in sheet
            if i.name in PHYLETIC_PARAM_NAMES and i.vocabulary()
        ),
        [],
    )
    displays = {option.value: option.display for option in tree}
    return [
        (c, label_term(c, displays[c])) for c in species_codes(value) if c in displays
    ]


def _pick_labels(terms: Sequence[str], info: ParameterInfo) -> list[tuple[str, str]]:
    options = info.vocabulary()
    displays = {option.value: option.display for option in options}
    return [
        (term, label_term(term, displays[match]))
        for term in terms
        if (match := match_exact_option(options, term)) is not None
    ]


def term_labels(
    value: ParamValue, info: ParameterInfo, sheet: Sequence[ParameterInfo]
) -> list[tuple[str, str]]:
    """Each term of the value the sheet labels, with its label, in the value's
    order. Only the site sets a read-only value, so the sheet labels none."""
    if info.name in PHYLETIC_PARAM_NAMES:
        return _tree_labels(value, sheet)
    if info.is_read_only:
        return []
    match value:
        case SinglePickValue(value=term):
            return _pick_labels([term], info)
        case MultiPickValue(values=terms):
            return _pick_labels(terms, info)
        case FilterValue(filters=clauses):
            displays = {f.term: f.display for f in info.filter_fields}
            return [
                (c.field, displays[c.field]) for c in clauses if c.field in displays
            ]
        case _:
            return []


def label_term(value: str, display: str) -> str:
    """The term a vocabulary label names: the label without a leading segment
    equal to the value and without a trailing integer depth."""
    segments = display.split(_SEGMENT)
    if len(segments) > 1 and segments[0].strip() == value:
        segments = segments[1:]
    if len(segments) > 1 and segments[-1].strip().isdigit():
        segments = segments[:-1]
    return _SEGMENT.join(segments).strip()


def value_label(
    value: ParamValue, info: ParameterInfo, sheet: Sequence[ParameterInfo]
) -> str:
    """The label of the value, or empty for a value that is its own label and
    for a term the vocabulary does not hold."""
    return _JOIN.join(label for _, label in term_labels(value, info, sheet))


__all__ = ["label_term", "species_codes", "term_labels", "value_label"]
