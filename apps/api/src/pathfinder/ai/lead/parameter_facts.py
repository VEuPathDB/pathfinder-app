"""The rows of a step's bound values, as a researcher reads them."""

from __future__ import annotations

from collections.abc import Sequence

from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    InputDatasetValue,
    MultiPickValue,
    to_wire,
)

from pathfinder.ai.lead.analysis_facts import analysis_parameters
from pathfinder.domain.log2_scale import fold_label
from pathfinder.domain.strategy.expression_handles import is_handle
from pathfinder.domain.strategy.measurement_clauses import (
    counted_clauses,
    read_pick_clauses,
)
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.option_labels import option_label
from pathfinder.domain.strategy.value_binding import plain_value
from pathfinder.domain.turn_facts import ParameterFact


def _label(criterion: Criterion, param: str, bound: BoundValue) -> str:
    """The label the vocabulary gives the value, else the fold a log2 value is."""
    return bound.label or fold_label(
        criterion.display_name_of(param), plain_value(bound.value)
    )


def _notes(criterion: Criterion, param: str, bound: BoundValue, noun: str) -> list[str]:
    """The measurements of a default or chosen value, the option of a card value,
    and for every value the pick taken from a vocabulary read."""
    match bound.source:
        case "default" | "chosen":
            return counted_clauses(criterion, param, noun=noun)
        case "card":
            return [
                option_label(criterion, param, to_wire(bound.value), noun=noun),
                *read_pick_clauses(criterion, param, noun=noun),
            ]
        case _:
            return read_pick_clauses(criterion, param, noun=noun)


def _shown(criterion: Criterion, name: str, bound: BoundValue) -> tuple[str, str, int]:
    """The value and its label as a researcher reads them. A list reads as what
    it holds, never as the site's id for it."""
    match bound.value:
        case InputDatasetValue():
            return bound.label or "an uploaded list", "", 1
        case _ if bound.taxon is not None:
            return bound.taxon.name, bound.taxon.label(), 1
        case _ if name == PHYLETIC_EXPRESSION_PARAM:
            return bound.label, "", 1
        case _ if bound.words:
            return bound.words, "", 1
        case MultiPickValue(values=values):
            return plain_value(bound.value), _label(criterion, name, bound), len(values)
        case _:
            return (
                bound.rounded() or plain_value(bound.value),
                _label(criterion, name, bound),
                1,
            )


def _parameter(
    criterion: Criterion, name: str, bound: BoundValue, noun: str
) -> ParameterFact:
    """One bound value's row. A placeholder the site left states no value, so
    it is shown as not set and nothing measures it. A pick a message names by
    its taxon is shown as that taxon and its organism count."""
    shown = criterion.display_name_of(name)
    if bound.placeholder:
        return ParameterFact(
            name=name,
            display_name=shown,
            value="not set",
            label="site placeholder",
            source=bound.source,
        )
    value, label, picks = _shown(criterion, name, bound)
    return ParameterFact(
        name=name,
        display_name=shown,
        value=value,
        label=label,
        source=bound.source,
        notes=_notes(criterion, name, bound, noun),
        picks=picks,
        expression=_expression(name, bound),
    )


def _expression(name: str, bound: BoundValue) -> str:
    if name != PHYLETIC_EXPRESSION_PARAM:
        return ""
    text = to_wire(bound.value)
    return "" if is_handle(text) else text


def step_parameters(
    criterion: Criterion, noun: str, said: Sequence[str]
) -> list[ParameterFact]:
    if criterion.analysis is not None:
        return analysis_parameters(criterion.analysis, said, noun)
    return [
        _parameter(criterion, name, bound, noun)
        for name, bound in criterion.shown_values.items()
    ]


__all__ = ["step_parameters"]
