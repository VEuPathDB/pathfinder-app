"""The label the site gives each bound value: a vocabulary display, a filter
field's display, or the organism a phyletic code names."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import (
    MAX_NEAREST_ENTRIES,
    FilterValue,
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    VocabOption,
    match_exact_option,
    nearest_entries,
    read_census,
    to_wire,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.services.strategies.parameter_rules import rules_of

# The literal the site writes for an empty species list.
_NO_SPECIES = "n/a"


class UnlabelledPick(BaseModel):
    """A pick its vocabulary gives no label, and the labels nearest to it."""

    model_config = ConfigDict(frozen=True)

    param: str
    term: str
    labels: list[str]


class VocabularyLabels(BaseModel):
    labels: list[Measurement]
    unlabelled: list[UnlabelledPick]


def pick_terms(value: ParamValue) -> list[str]:
    """The vocabulary terms a pick holds; none for any other value."""
    match value:
        case MultiPickValue(values=values):
            return list(values)
        case SinglePickValue(value=term):
            return [term]
        case _:
            return []


def _label(name: str, term: str, label: str) -> Measurement:
    return Measurement(kind="vocabulary_label", param=name, label=label, reading=term)


def _filter_labels(
    name: str, value: ParamValue, info: ParameterInfo
) -> VocabularyLabels:
    """The label of each clause is the display of the field it names.

    A member value is its own label, so the capped value list is not read.
    """
    match value:
        case FilterValue(filters=clauses):
            pass
        case _:
            clauses = []
    displays = {f.term: f.display for f in info.filter_fields}
    labels: list[Measurement] = []
    unlabelled: list[UnlabelledPick] = []
    for clause in clauses:
        if clause.field in displays:
            labels.append(_label(name, clause.field, displays[clause.field]))
        else:
            unlabelled.append(
                UnlabelledPick(
                    param=name, term=clause.field, labels=list(displays.values())
                )
            )
    return VocabularyLabels(labels=labels, unlabelled=unlabelled)


def _pick_labels(name: str, value: ParamValue, info: ParameterInfo) -> VocabularyLabels:
    options = info.vocabulary()
    displays = {option.value: option.display for option in options}
    labels: list[Measurement] = []
    unlabelled: list[UnlabelledPick] = []
    for term in pick_terms(value):
        match = match_exact_option(options, term)
        if match is not None:
            labels.append(_label(name, term, displays[match]))
        elif options:
            near = set(nearest_entries(options, term, MAX_NEAREST_ENTRIES))
            unlabelled.append(
                UnlabelledPick(
                    param=name,
                    term=term,
                    labels=[o.display for o in options if {o.value, o.display} & near],
                )
            )
    return VocabularyLabels(labels=labels, unlabelled=unlabelled)


def _codes(value: ParamValue) -> list[str]:
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
    name: str, value: ParamValue, tree: Sequence[VocabOption]
) -> VocabularyLabels:
    """The organism the clade tree names each code by."""
    displays = {option.value: option.display for option in tree}
    return VocabularyLabels(
        labels=[_label(name, c, displays[c]) for c in _codes(value) if c in displays],
        unlabelled=[],
    )


def vocabulary_labels(
    values: Mapping[str, BoundValue], infos: Sequence[ParameterInfo]
) -> VocabularyLabels:
    """The label the site gives each bound value, whoever set it.

    A pick reads its vocabulary, a filter clause its field, and a phyletic code
    the clade tree the species lists carry. A value that is its own label, or
    whose vocabulary the site did not publish, has no label to read.
    """
    by_name = {info.name: info for info in infos}
    tree = next(
        (
            i.vocabulary()
            for i in infos
            if rules_of(i).label == "tree_organism" and i.vocabulary()
        ),
        [],
    )
    labels: list[Measurement] = []
    unlabelled: list[UnlabelledPick] = []
    for name, bound in values.items():
        info = by_name.get(name)
        if info is None:
            continue
        match rules_of(info).label:
            case "vocabulary_display":
                read = _pick_labels(name, bound.value, info)
            case "filter_field_display":
                read = _filter_labels(name, bound.value, info)
            case "tree_organism":
                read = _tree_labels(name, bound.value, tree)
            case "own_label":
                continue
        labels.extend(read.labels)
        unlabelled.extend(read.unlabelled)
    return VocabularyLabels(labels=labels, unlabelled=unlabelled)


__all__ = [
    "UnlabelledPick",
    "VocabularyLabels",
    "pick_terms",
    "vocabulary_labels",
]
