"""A search whose marked parameter lists samples under organism branches gives no
organism scope, so its INTERSECT with a dataset search of one organism stands.

Gated on WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD (skipped unset).
"""

from __future__ import annotations

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.strategy.validate import first_cross_organism_refusal
from pathfinder.services.strategies.organism_params import (
    tree_dataset_organisms,
    tree_organism_parameters,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SCHIZONT_RNASEQ = (
    "GenesByRNASeqpfal3D7_Josling_Schizont_Transcriptomes_ebi_rnaSeq_RSRCPercentile"
)


def _tree() -> StrategyStepNode:
    mass_spec = StrategyStepNode(
        search_name="GenesByMassSpec",
        parameters={
            "ms_assay": MultiPickValue(
                values=["merozoite proteome (3D7)_Plasmodium falciparum 3D7"]
            )
        },
    )
    return StrategyStepNode(
        search_name="boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(id="schizont", search_name=_SCHIZONT_RNASEQ),
        secondary_input=mass_spec,
    )


async def test_a_mass_spec_search_marks_no_organism_and_its_intersect_stands(
    require_wdk_creds: str,
    patch_app_db_engine: None,
) -> None:
    del patch_app_db_engine
    tree = _tree()
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        marks = await tree_organism_parameters("plasmodb", "transcript", tree)
        datasets = await tree_dataset_organisms("plasmodb", tree, marks)
    finally:
        veupathdb_auth_token_ctx.reset(handle)

    assert "GenesByMassSpec" not in marks
    assert datasets["schizont"] == frozenset({"Plasmodium falciparum 3D7"})
    assert first_cross_organism_refusal(tree, marks, datasets) is None
