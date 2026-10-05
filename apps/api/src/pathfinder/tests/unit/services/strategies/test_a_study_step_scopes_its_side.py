"""A study step runs on the organisms of its study's dataset record, read by step
id, so two studies on one generic search keep two scopes."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode
from veupathdb_mcp.catalog import COMPUTE_QUERY, EDA_DATASET_ID_PARAM

from pathfinder.domain.strategy.validate import first_cross_organism_refusal
from pathfinder.services.strategies.organism_params import (
    step_dataset_organisms,
    tree_dataset_organisms,
)
from pathfinder.tests._support.organism_reads import (
    GT1,
    ME49,
    ME49_STUDY,
    UNKNOWN_STUDY,
)

_DOMAIN = "GenesByInterproDomain"
_MARKED = {_DOMAIN: "organism"}


def _study(step_id: str, dataset_id: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=COMPUTE_QUERY,
        parameters={EDA_DATASET_ID_PARAM: StringValue(value=dataset_id)},
    )


def _domain(organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="domain",
        search_name=_DOMAIN,
        parameters={"organism": MultiPickValue(values=[organism])},
    )


def _intersect(left: StrategyStepNode, right: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id="both",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=left,
        secondary_input=right,
    )


async def test_a_study_step_runs_on_its_studys_organisms() -> None:
    assert await step_dataset_organisms(
        "toxodb", COMPUTE_QUERY, _study("study", ME49_STUDY).parameters
    ) == [ME49]


async def test_a_study_the_store_holds_no_card_for_has_no_scope() -> None:
    assert (
        await step_dataset_organisms(
            "toxodb", COMPUTE_QUERY, _study("study", UNKNOWN_STUDY).parameters
        )
        == []
    )


async def test_each_study_step_is_scoped_by_its_own_id() -> None:
    root = _intersect(_study("me49", ME49_STUDY), _study("unread", UNKNOWN_STUDY))

    assert await tree_dataset_organisms("toxodb", root, {}) == {
        "me49": frozenset({ME49})
    }


async def test_another_strain_beside_a_study_is_refused_with_the_orthology_remedy() -> (
    None
):
    root = _intersect(_domain(GT1), _study("study", ME49_STUDY))

    datasets = await tree_dataset_organisms("toxodb", root, _MARKED)

    assert first_cross_organism_refusal(root, _MARKED, datasets) == (
        f"Cannot INTERSECT steps with different organism scopes ({GT1} vs {ME49}). "
        f"Gene IDs from different organisms never match, so this always returns 0 "
        f"results. The {COMPUTE_QUERY} search runs on an experiment of {ME49}, and "
        f"no parameter changes that organism. Map that side to {GT1} with a "
        f"GenesByOrthologs transform."
    )


async def test_the_studys_own_strain_is_not_refused() -> None:
    root = _intersect(_domain(ME49), _study("study", ME49_STUDY))

    datasets = await tree_dataset_organisms("toxodb", root, _MARKED)

    assert (datasets, first_cross_organism_refusal(root, _MARKED, datasets)) == (
        {"study": frozenset({ME49})},
        None,
    )
