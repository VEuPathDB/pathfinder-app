"""How each class of WDK parameter is measured, labelled and sourced, total
over the parameter kinds WDK publishes."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import (
    PHYLETIC_LIST_PARAMS,
    PHYLETIC_PARAM_NAMES,
    ParamKind,
    ParamValue,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.value_source import is_unset

MeasurementRule = Literal[
    "loosest_bound",
    "phrase_reach",
    "species_lists",
    "site_default",
    "site_fixed",
    "not_measurable",
]
LabelRule = Literal[
    "vocabulary_display",
    "filter_field_display",
    "tree_organism",
    "own_label",
]
SourceRule = Literal["words", "site"]
ParameterClass = (
    ParamKind
    | Literal[
        "numeric_string", "tree_pick", "phyletic_list", "phyletic_pattern", "site_fixed"
    ]
)


class ParameterRules(BaseModel):
    """How a value of one parameter class is measured, where its label is read,
    and who can set it. ``reason`` says why a value has no reading, or why a
    pick names no options not taken."""

    model_config = ConfigDict(frozen=True)

    measurement: MeasurementRule
    label: LabelRule
    source: SourceRule = "words"
    reason: str = ""


_DATE = ParameterRules(
    measurement="not_measurable",
    label="own_label",
    reason="the site publishes no bound to read a date at",
)
_PICK = ParameterRules(measurement="site_default", label="vocabulary_display")

PARAMETER_RULES: Mapping[ParameterClass, ParameterRules] = MappingProxyType(
    {
        "string": ParameterRules(measurement="phrase_reach", label="own_label"),
        "numeric_string": ParameterRules(
            measurement="loosest_bound", label="own_label"
        ),
        "number": ParameterRules(measurement="loosest_bound", label="own_label"),
        "number-range": ParameterRules(measurement="loosest_bound", label="own_label"),
        "date": _DATE,
        "date-range": _DATE,
        "timestamp": _DATE,
        "single-pick-vocabulary": _PICK,
        "multi-pick-vocabulary": _PICK,
        "tree_pick": ParameterRules(
            measurement="site_default",
            label="vocabulary_display",
            reason=(
                "options not taken: not applicable, since a parent term takes the "
                "options under it"
            ),
        ),
        "filter": ParameterRules(
            measurement="site_default", label="filter_field_display"
        ),
        "input-dataset": ParameterRules(
            measurement="not_measurable",
            label="own_label",
            reason="an uploaded dataset has no other reading",
        ),
        "input-step": ParameterRules(
            measurement="not_measurable",
            label="own_label",
            reason="a step input is another step's result",
        ),
        "phyletic_list": ParameterRules(
            measurement="species_lists", label="tree_organism"
        ),
        "phyletic_pattern": ParameterRules(
            measurement="not_measurable",
            label="tree_organism",
            reason="the pattern is derived from the species lists",
        ),
        "site_fixed": ParameterRules(
            measurement="site_fixed", label="own_label", source="site"
        ),
    }
)


def site_fixed(info: ParameterInfo) -> bool:
    """A read-only parameter, or a hidden one with no vocabulary, holds a value
    only the site sets.

    Hidden means not shown: a hidden parameter with a vocabulary takes any of
    its entries.
    """
    return info.is_read_only or (not info.is_visible and not info.vocabulary())


def parameter_class(info: ParameterInfo) -> ParameterClass:
    if info.name in PHYLETIC_LIST_PARAMS:
        return "phyletic_list"
    if info.name in PHYLETIC_PARAM_NAMES:
        return "phyletic_pattern"
    if site_fixed(info):
        return "site_fixed"
    if info.param_kind == "string" and info.is_number:
        return "numeric_string"
    if info.allowed_values_tree is not None:
        return "tree_pick"
    return info.param_kind


def rules_of(info: ParameterInfo) -> ParameterRules:
    return PARAMETER_RULES[parameter_class(info)]


def text_query(info: ParameterInfo, value: ParamValue) -> bool:
    """Whether the value is a text query: a free-text value that is not unset."""
    return parameter_class(info) == "string" and not is_unset(
        value, info.default_value, info
    )


__all__ = [
    "PARAMETER_RULES",
    "LabelRule",
    "MeasurementRule",
    "ParameterClass",
    "ParameterRules",
    "SourceRule",
    "parameter_class",
    "rules_of",
    "site_fixed",
    "text_query",
]
