from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.export import ExportReading
from pathfinder.services.eda.steps import eda_step_node, on_the_sites_own_search
from pathfinder.tests._support.eda_step_doubles import de_analysis, phenotype_subset
from pathfinder.tests._support.eda_subset_search_doubles import (
    serve_plasmodb_subset_searches,
)

_OWN = "GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC"


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return serve_plasmodb_subset_searches(monkeypatch)


async def test_a_subset_of_a_curated_study_runs_the_datasets_own_search(
    asked: list[str],
) -> None:
    del asked
    plan = eda_step_node(
        phenotype_subset(),
        dataset_id="DS_53f554ec6a",
        thresholds=None,
        reading=ExportReading(),
    )

    routed = await on_the_sites_own_search("plasmodb", plan)

    assert routed.node.search_name == _OWN
    assert routed.node.parameters == plan.node.parameters
    assert (routed.stamped.search_name, routed.stamped.kind) == (
        _OWN,
        AnalysisKind.SUBSET,
    )


async def test_a_study_the_site_has_no_search_for_keeps_the_generic_subset(
    asked: list[str],
) -> None:
    del asked
    detail = phenotype_subset().model_copy(update={"study_id": "DS_0000000000"})
    plan = eda_step_node(
        detail,
        dataset_id="DS_0000000000",
        thresholds=None,
        reading=ExportReading(),
    )

    routed = await on_the_sites_own_search("plasmodb", plan)

    assert routed.node.search_name == SUBSET_QUERY


async def test_a_volcano_export_keeps_the_compute_search_and_reads_no_definition(
    asked: list[str],
) -> None:
    plan = eda_step_node(
        de_analysis(filters=[], with_computation=True),
        dataset_id="DS_e973eadd57",
        thresholds=VolcanoThresholds(
            effect_size_threshold=1.0,
            significance_threshold=0.05,
            effect_direction="upAndDown",
        ),
        reading=ExportReading(),
    )

    routed = await on_the_sites_own_search("plasmodb", plan)

    assert (routed.node.search_name, asked) == (COMPUTE_QUERY, [])
