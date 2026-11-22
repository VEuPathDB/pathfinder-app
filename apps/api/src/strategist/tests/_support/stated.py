"""Typed test values as the model states them."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StrategyStepNode

from strategist.ai.tools.standalone._stated_values import StatedStepNode


def stated(values: Mapping[str, ParamValue]) -> dict[str, JsonValue]:
    return {name: value.to_decoded() for name, value in values.items()}


def stated_tree(node: StrategyStepNode) -> StatedStepNode:
    inputs = (node.primary_input, node.secondary_input)
    primary, secondary = (None if n is None else stated_tree(n) for n in inputs)
    return StatedStepNode(
        id=node.id,
        search_name=node.search_name,
        parameters=stated(node.parameters),
        primary_input=primary,
        secondary_input=secondary,
        operator=node.operator,
        colocation_params=node.colocation_params,
        display_name=node.display_name,
        wdk_weight=node.wdk_weight,
    )
