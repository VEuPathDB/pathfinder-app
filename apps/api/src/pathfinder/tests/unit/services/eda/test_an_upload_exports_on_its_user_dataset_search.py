"""An export of the researcher's own upload runs the site's user-dataset search
of the upload's type; a curated study keeps the generic export."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from veupathdb_mcp.catalog import COMPUTE_QUERY

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.export import ExportReading
from pathfinder.services.eda.steps import eda_step_node, on_the_user_dataset_search
from pathfinder.tests._support.eda_step_doubles import de_analysis
from pathfinder.tests._support.user_dataset_doubles import (
    UPLOAD_DATASET,
    wire_plasmodb_uploads,
)

_CUT = VolcanoThresholds(
    effect_size_threshold=5.0, significance_threshold=1e-10, effect_direction="upOnly"
)


@pytest.fixture
def plasmodb(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    return wire_plasmodb_uploads(monkeypatch)


@pytest.mark.asyncio
async def test_a_volcano_export_of_an_upload_runs_the_deseq_user_dataset_search(
    plasmodb: AsyncMock,
) -> None:
    del plasmodb
    plan = eda_step_node(
        de_analysis(filters=[], with_computation=True),
        dataset_id=UPLOAD_DATASET,
        thresholds=_CUT,
        reading=ExportReading(),
    )

    routed = await on_the_user_dataset_search("plasmodb", plan)

    assert routed.node.search_name == "GenesByDESeqUserDataset"
    assert routed.node.parameters == plan.node.parameters
    assert routed.stamped.search_name == "GenesByDESeqUserDataset"
    assert routed.stamped.kind is AnalysisKind.COMPUTE
    assert routed.binding.effect_size_threshold == 5.0


@pytest.mark.asyncio
async def test_a_curated_study_keeps_the_generic_export_and_reads_no_uploads(
    plasmodb: AsyncMock,
) -> None:
    plan = eda_step_node(
        de_analysis(filters=[], with_computation=True),
        dataset_id="DS_e973eadd57",
        thresholds=_CUT,
        reading=ExportReading(),
    )

    routed = await on_the_user_dataset_search("plasmodb", plan)

    assert routed.node.search_name == COMPUTE_QUERY
    plasmodb.assert_not_awaited()
