"""create_eda_step writes an export of the researcher's own upload on the site's
user-dataset search of the upload's type, as the analysis tab's export does."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.eda import EdaVolcanoConfiguration
from veupathdb_mcp.catalog import COMPUTE_QUERY

from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.operations.types import AddLeafOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.eda_step_doubles import (
    DE_DATASET,
    de_analysis,
    pushing_commit,
    wire_analysis,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.user_dataset_doubles import (
    UPLOAD_DATASET,
    wire_plasmodb_uploads,
)


async def _exported_search(monkeypatch: pytest.MonkeyPatch, dataset_id: str) -> str:
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("g1", "Test", "plasmodb"))
    applied: list[Any] = []
    analysis = de_analysis(
        filters=[],
        with_computation=True,
        volcano=EdaVolcanoConfiguration(
            effect_size_threshold=1.0,
            significance_threshold=0.05,
            effect_direction="upOnly",
            effect_size_label="log2(Fold Change)",
        ),
    ).model_copy(update={"study_id": dataset_id})
    wire_analysis(monkeypatch, eda_step, analysis)
    wire_plasmodb_uploads(monkeypatch)
    monkeypatch.setattr(
        eda_step,
        "apply_operations_and_commit",
        pushing_commit(applied, session=session, count=40),
    )

    await eda_step.create_eda_step(
        lead_run_context(user_prompt="export the up genes", strategy_session=session),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="upOnly",
        caption="Genes higher in normal than in febrile",
    )

    [op] = applied[0]
    assert isinstance(op, AddLeafOp)
    return op.step.search_name


async def test_an_export_of_an_upload_runs_the_deseq_user_dataset_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        await _exported_search(monkeypatch, UPLOAD_DATASET) == "GenesByDESeqUserDataset"
    )


async def test_an_export_of_a_curated_study_keeps_the_generic_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _exported_search(monkeypatch, DE_DATASET) == COMPUTE_QUERY
