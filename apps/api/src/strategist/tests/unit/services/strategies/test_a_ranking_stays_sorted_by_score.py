from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, flatten_tree

from strategist.domain.strategy.operations import DeleteResolution, DeleteStepOp
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies.commit import apply_and_commit
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.wdk_write_stubs import put_the_graph
from strategist.tests.unit.services.strategies.test_commit_reroots_the_strategy import (
    _join,
    _leaf,
    _RecordingAPI,
    _seed,
    api,
)

__all__ = ["api"]


@pytest.mark.asyncio
async def test_a_ranking_a_removal_re_roots_is_sorted_by_score(
    api: _RecordingAPI,
) -> None:
    step_a = _leaf("step_a", "GenesByMolecularWeight").model_copy(
        update={"wdk_weight": 2}
    )
    step_b = _leaf("step_b", "GenesByTaxon").model_copy(update={"wdk_weight": 1})
    root = _join("step_join", step_a, step_b, CombineOp.UNION)
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 300}, api)

    await apply_and_commit(
        deps=deps,
        op=DeleteStepOp(step_id="step_b", resolution=DeleteResolution.COLLAPSE_COMBINE),
    )

    assert [
        (call.kwargs["step_id"], call.kwargs["spec"].model_dump(exclude_none=True))
        for call in api.named("update_step_properties")
    ] == [
        (
            100,
            {
                "display_preferences": {
                    "sort_columns": [{"name": "wdk_weight", "direction": "DESC"}]
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_an_unweighted_removal_keeps_the_sites_sort(api: _RecordingAPI) -> None:
    root = _join(
        "step_join",
        _leaf("step_a", "GenesByMolecularWeight"),
        _leaf("step_b", "GenesByTaxon"),
        CombineOp.UNION,
    )
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 300}, api)

    await apply_and_commit(
        deps=deps,
        op=DeleteStepOp(step_id="step_b", resolution=DeleteResolution.COLLAPSE_COMBINE),
    )

    assert api.named("update_step_properties") == []


@pytest.mark.asyncio
async def test_a_new_ranking_opens_sorted_by_score(api: _RecordingAPI) -> None:
    root = _join(
        "step_join",
        _leaf("step_a", "GenesByMolecularWeight").model_copy(update={"wdk_weight": 1}),
        _leaf("step_b", "GenesByTaxon").model_copy(update={"wdk_weight": 1}),
        CombineOp.UNION,
    )
    graph = StrategyGraph(graph_id="g1", name="Test", site_id="toxodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()

    await put_the_graph(
        graph,
        WDKSyncState(wdk_step_ids={"step_a": 100, "step_b": 200, "step_join": 300}),
        "toxodb",
    )

    assert [call.kwargs["step_id"] for call in api.named("update_step_properties")] == [
        300
    ]
