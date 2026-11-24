from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.domain.strategy import CombineOp, flatten_tree
from veupathdb.errors import WDKError

from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import commit_tree
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.wdk_write_stubs import put_the_graph
from strategist.tests.unit.services.strategies.test_commit_reroots_the_strategy import (
    _join,
    _leaf,
    _RecordingAPI,
    api,
)

__all__ = ["api"]

_REFUSED = WDKError("the step does not take a sort", status=422)


async def _refused(*_args: object) -> NoReturn:
    raise _REFUSED


async def test_a_ranking_the_site_did_not_sort_is_a_failed_root(
    api: _RecordingAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commit_tree, "_sort_a_ranking", _refused)
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
    state = WDKSyncState(wdk_step_ids={"step_a": 100, "step_b": 200, "step_join": 300})
    api.holds(graph.steps, state)

    committed = await put_the_graph(graph, state, "toxodb")

    assert committed.failures == [
        StepPushFailure(
            step_id="step_join",
            search_name="__combine__",
            error=(
                "ToxoDB (Toxoplasma) did not sort the ranked result by score, so it "
                "is not ranked: HTTP 422: VEuPathDB service error: the step does not "
                "take a sort"
            ),
        )
    ]
