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
    nearest_entries,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.domain.strategy.value_label import term_labels
from pathfinder.services.strategies.parameter_rules import rules_of


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


def _nearest(options: Sequence[VocabOption], term: str) -> list[str]:
    near = set(nearest_entries(options, term, MAX_NEAREST_ENTRIES))
    return [o.display for o in options if {o.value, o.display} & near]


def _unlabelled(
    name: str, value: ParamValue, info: ParameterInfo, labelled: set[str]
) -> list[UnlabelledPick]:
    """Each pick or filter clause the sheet gives no label, with the labels
    nearest to it; a clause names every field the parameter has."""
    match rules_of(info).label, value:
        case "filter_field_display", FilterValue(filters=clauses):
            fields = [f.display for f in info.filter_fields]
            return [
                UnlabelledPick(param=name, term=c.field, labels=fields)
                for c in clauses
                if c.field not in labelled
            ]
        case "vocabulary_display", _:
            options = info.vocabulary()
            return [
                UnlabelledPick(param=name, term=term, labels=_nearest(options, term))
                for term in pick_terms(value)
                if options and term not in labelled
            ]
        case _:
            return []


def vocabulary_labels(
    values: Mapping[str, BoundValue], infos: Sequence[ParameterInfo]
) -> VocabularyLabels:
    """The label the site gives each term of each bound value, whoever set it,
    read as the bound value's own label is read."""
    by_name = {info.name: info for info in infos}
    labels: list[Measurement] = []
    unlabelled: list[UnlabelledPick] = []
    for name, bound in values.items():
        info = by_name.get(name)
        if info is None or rules_of(info).label == "own_label":
            continue
        read = term_labels(bound.value, info, infos)
        labels.extend(
            Measurement(kind="vocabulary_label", param=name, label=label, reading=term)
            for term, label in read
        )
        unlabelled.extend(
            _unlabelled(name, bound.value, info, {term for term, _ in read})
        )
    return VocabularyLabels(labels=labels, unlabelled=unlabelled)


__all__ = [
    "UnlabelledPick",
    "VocabularyLabels",
    "pick_terms",
    "vocabulary_labels",
]
