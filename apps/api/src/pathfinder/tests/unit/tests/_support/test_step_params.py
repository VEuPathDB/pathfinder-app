"""The string reader for a step's parameters."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.tests._support.step_params import string_param


def _node(name: str, value: StringValue | NumberValue) -> StrategyStepNode:
    return StrategyStepNode(search_name="GenesByTaxon", parameters={name: value})


def test_it_reads_the_text_a_string_parameter_holds() -> None:
    node = _node("organism", StringValue(value="Plasmodium falciparum"))

    assert string_param(node, "organism") == "Plasmodium falciparum"


def test_it_names_the_shape_a_parameter_holds_when_it_is_not_a_string() -> None:
    node = _node("cutoff", NumberValue(value=3))

    with pytest.raises(AssertionError, match="cutoff holds NumberValue"):
        string_param(node, "cutoff")


def test_it_raises_a_key_error_for_a_parameter_the_step_does_not_carry() -> None:
    node = _node("organism", StringValue(value="Plasmodium berghei"))

    with pytest.raises(KeyError):
        string_param(node, "absent")
