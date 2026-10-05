"""A study step runs on the organisms of its study's dataset record on the site,
so its INTERSECT with a search on another strain is refused before a push.

Gated on WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD (skipped unset).
"""

from __future__ import annotations

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode
from veupathdb_mcp.catalog import COMPUTE_QUERY, EDA_DATASET_ID_PARAM

from pathfinder.domain.strategy.validate import first_cross_organism_refusal
from pathfinder.services.strategies.organism_params import (
    tree_dataset_organisms,
    tree_organism_parameters,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

# toxodb's master regulator of sexual commitment RNA-Seq study, an ME49 record.
_ME49_STUDY = "DS_749cb10dcf"


def _tree(organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="both",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="domain",
            search_name="GenesByInterproDomain",
            parameters={"organism": MultiPickValue(values=[organism])},
        ),
        secondary_input=StrategyStepNode(
            id="study",
            search_name=COMPUTE_QUERY,
            parameters={EDA_DATASET_ID_PARAM: StringValue(value=_ME49_STUDY)},
        ),
    )


async def _refusal(organism: str) -> tuple[frozenset[str], str | None]:
    tree = _tree(organism)
    marks = await tree_organism_parameters("toxodb", "transcript", tree)
    datasets = await tree_dataset_organisms("toxodb", tree, marks)
    return datasets["study"], first_cross_organism_refusal(tree, marks, datasets)


async def test_a_study_step_on_toxodb_scopes_to_its_records_strain(
    require_wdk_creds: str,
    patch_app_db_engine: None,
) -> None:
    del patch_app_db_engine
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        gt1 = await _refusal("Toxoplasma gondii GT1")
        me49 = await _refusal("Toxoplasma gondii ME49")
    finally:
        veupathdb_auth_token_ctx.reset(handle)

    assert gt1[0] == frozenset({"Toxoplasma gondii ME49"})
    assert gt1[1] is not None
    assert "Toxoplasma gondii GT1 vs Toxoplasma gondii ME49" in gt1[1]
    assert me49[1] is None
