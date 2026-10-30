"""A push applies a step's filters and runs none of its reports."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from veupathdb.domain.strategy import (
    StepFilter,
    StepReport,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import StrategyAPI, WDKIdentifier, WDKStrategyDetails

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import sync
from pathfinder.services.strategies.sync import sync_strategy_for_site
from pathfinder.services.strategies.sync_state import WDKSyncState

_WDK_STEP_ID = 227284190
_STRATEGY_ID = 214645070


def _details() -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": _STRATEGY_ID,
            "rootStepId": _WDK_STEP_ID,
            "name": "test",
            "stepTree": {"stepId": _WDK_STEP_ID},
            "steps": {
                str(_WDK_STEP_ID): {
                    "id": _WDK_STEP_ID,
                    "searchName": "GenesByMolecularWeight",
                    "searchConfig": {"parameters": {}},
                    "estimatedSize": 4456,
                }
            },
            "recordClassName": "transcript",
        }
    )


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Mock:
    stub = Mock(spec=StrategyAPI)
    stub.create_strategy = AsyncMock(return_value=WDKIdentifier(id=_STRATEGY_ID))
    stub.get_strategy = AsyncMock(return_value=_details())
    stub.set_step_filter = AsyncMock(return_value=None)
    stub.run_step_report = AsyncMock(return_value={})
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: stub)
    return stub


def _graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "test", "plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="A",
            search_name="GenesByMolecularWeight",
            filters=[StepFilter(name="matched_transcript_filter_array", value={})],
            reports=[
                StepReport(report_name="standard"),
                StepReport(report_name="fullRecord"),
            ],
        )
    )
    graph.steps["A"].record_class = "transcript"
    graph.record_type = "transcript"
    graph.recompute_roots()
    return graph


async def test_a_push_applies_the_filter_and_runs_no_report(api: Mock) -> None:
    await sync_strategy_for_site(
        graph=_graph(),
        sync_state=WDKSyncState(wdk_step_ids={"A": _WDK_STEP_ID}),
        site_id="plasmodb",
    )

    assert api.set_step_filter.await_count == 1
    assert api.run_step_report.await_count == 0
