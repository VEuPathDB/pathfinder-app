"""A phyletic expression read back in words, with the size of each list it counts
across, so a count that does not match the request shows."""

from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.parameters import PhyleticTree, to_wire
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.expression_handles import (
    expression_reading,
    shown_wire,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Measurement,
)
from pathfinder.services.strategies.parameter_rules import rules_of


def expression_readings(
    values: Mapping[str, BoundValue],
    infos: Mapping[str, ParameterInfo],
    tree: PhyleticTree | None,
) -> list[Measurement]:
    """The reading of each expression value. It needs no count from the site."""
    readings: list[Measurement] = []
    for name, bound in values.items():
        if name not in infos or bound.unset:
            continue
        if rules_of(infos[name]).measurement != "expression_reading":
            continue
        text = to_wire(bound.value)
        readings.append(
            Measurement(
                kind="vocabulary_label",
                param=name,
                reading=shown_wire(name, text),
                label=expression_reading(text, tree or PhyleticTree()),
            )
        )
    return readings
