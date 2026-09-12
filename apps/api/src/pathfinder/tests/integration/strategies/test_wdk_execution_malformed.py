from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.tests.integration.strategies.conftest import BuildRaw

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_ORGANISM = "Plasmodium falciparum 3D7"


def _good_text_leaf(step_id: str = "good") -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByText",
        parameters={
            "text_expression": StringValue(value="kinase"),
            "text_fields": MultiPickValue(values=["product"]),
            "document_type": StringValue(value="gene"),
            "text_search_organism": MultiPickValue(values=[_ORGANISM]),
        },
    )


def _invalid_search_leaf(step_id: str = "bad") -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByNonexistentSearch",
        parameters={"text_expression": StringValue(value="kinase")},
    )


def _unknown_param_leaf(step_id: str = "bad") -> StrategyStepNode:
    leaf = _good_text_leaf(step_id)
    leaf.parameters["totally_bogus_param"] = StringValue(value="x")
    return leaf


def _bad_vocab_leaf(step_id: str = "bad") -> StrategyStepNode:
    leaf = _good_text_leaf(step_id)
    leaf.parameters["text_fields"] = MultiPickValue(values=["not_a_real_field"])
    return leaf


async def test_empty_params_leaf_fails_at_build(wdk_build_raw: BuildRaw) -> None:
    leaf = StrategyStepNode(id="bad", search_name="GenesByText", parameters={})

    outcome = await wdk_build_raw(leaf)

    assert outcome.wdk_strategy_id is None
    assert [f.step_id for f in outcome.failed_steps] == ["bad"]
    assert outcome.failed_steps[0].error.strip()
    assert outcome.pushed_step_ids == []


async def test_invalid_search_name_fails_the_step(wdk_build_raw: BuildRaw) -> None:
    outcome = await wdk_build_raw(_invalid_search_leaf())

    assert outcome.wdk_strategy_id is None
    assert [f.step_id for f in outcome.failed_steps] == ["bad"]
    failure = outcome.failed_steps[0]
    assert failure.search_name == "GenesByNonexistentSearch"
    assert "Search name not found" in failure.error
    assert outcome.pushed_step_ids == []


async def test_unknown_parameter_fails_the_step(wdk_build_raw: BuildRaw) -> None:
    outcome = await wdk_build_raw(_unknown_param_leaf())

    assert outcome.wdk_strategy_id is None
    assert [f.step_id for f in outcome.failed_steps] == ["bad"]
    error = outcome.failed_steps[0].error
    assert "totally_bogus_param" in error
    assert "does not exist for this search" in error


async def test_invalid_field_vocab_value_fails_the_step(
    wdk_build_raw: BuildRaw,
) -> None:
    outcome = await wdk_build_raw(_bad_vocab_leaf())

    assert outcome.wdk_strategy_id is None
    assert [f.step_id for f in outcome.failed_steps] == ["bad"]
    assert outcome.failed_steps[0].error.strip()


async def test_combine_over_a_broken_leaf_skips_the_combine(
    wdk_build_raw: BuildRaw,
) -> None:
    good = _good_text_leaf("good")
    bad = _invalid_search_leaf("bad")
    combine = StrategyStepNode(
        id="combine",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=good,
        secondary_input=bad,
    )

    outcome = await wdk_build_raw(combine)

    assert outcome.wdk_strategy_id is None
    assert [f.step_id for f in outcome.failed_steps] == ["bad"]
    assert "good" in outcome.pushed_step_ids
    assert "combine" in outcome.skipped_step_ids
