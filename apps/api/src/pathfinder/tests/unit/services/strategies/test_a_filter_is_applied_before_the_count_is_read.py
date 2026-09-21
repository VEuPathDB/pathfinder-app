"""A filtered step records the size it has once the filter is on it.

A filter narrows what a step answers, and the site applies it on the step
rather than on the tree. A count read before the filter reaches the site
describes the unfiltered step, and that number is what the sync stores.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from veupathdb.domain.strategy import StepFilter, StrategyStepNode, flatten_tree
from veupathdb.wdk import (
    SiteInfo,
    StrategyAPI,
    WDKIdentifier,
    WDKStrategyDetails,
)

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import sync
from pathfinder.services.strategies.sync import SyncResult, sync_strategy_for_site
from pathfinder.services.strategies.sync_state import WDKSyncState

_STEP = "step_text"
_WDK_STEP_ID = 1001
_STRATEGY = 77
_UNFILTERED = 1825
_FILTERED = 71

_SITE = SiteInfo(
    id="plasmodb",
    name="plasmodb",
    display_name="PlasmoDB",
    base_url="https://plasmodb.org/plasmo/service",
    project_id="PlasmoDB",
    is_portal=False,
)


class _Site:
    """A site whose step answers fewer records once its filter is set."""

    def __init__(self) -> None:
        self.filtered = False

    def details(self) -> WDKStrategyDetails:
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": _STRATEGY,
                "rootStepId": _WDK_STEP_ID,
                "name": "test",
                "stepTree": {"stepId": _WDK_STEP_ID},
                "steps": {
                    str(_WDK_STEP_ID): {
                        "id": _WDK_STEP_ID,
                        "searchName": "GenesByText",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": _FILTERED if self.filtered else _UNFILTERED,
                    }
                },
                "recordClassName": "transcript",
            }
        )


def _api(site: _Site) -> StrategyAPI:
    api = Mock(spec=StrategyAPI)

    async def create_strategy(*_args: object, **_kwargs: object) -> WDKIdentifier:
        return WDKIdentifier(id=_STRATEGY)

    async def get_strategy(*_args: object, **_kwargs: object) -> WDKStrategyDetails:
        return site.details()

    async def set_step_filter(*_args: object, **_kwargs: object) -> None:
        site.filtered = True

    api.create_strategy = AsyncMock(side_effect=create_strategy)
    api.get_strategy = AsyncMock(side_effect=get_strategy)
    api.set_step_filter = AsyncMock(side_effect=set_step_filter)
    api.update_strategy = AsyncMock(side_effect=NotImplementedError)
    return api


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> _Site:
    served = _Site()
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: _api(served))
    monkeypatch.setattr(sync, "get_site", lambda _site_id: _SITE)
    return served


def _graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "test", "plasmodb")
    step = StrategyStepNode(
        id=_STEP,
        search_name="GenesByText",
        filters=[StepFilter(name="gene_boolean_filter_array", value={"values": ["x"]})],
    )
    graph.steps = flatten_tree(step)
    graph.steps[_STEP].record_class = "transcript"
    graph.record_type = "transcript"
    graph.recompute_roots()
    return graph


async def _sync(sync_state: WDKSyncState) -> SyncResult:
    return await sync_strategy_for_site(
        graph=_graph(), sync_state=sync_state, site_id="plasmodb"
    )


@pytest.mark.asyncio
async def test_the_session_records_the_filtered_size(site: _Site) -> None:
    sync_state = WDKSyncState(wdk_step_ids={_STEP: _WDK_STEP_ID})

    await _sync(sync_state)

    assert sync_state.step_counts == {_STEP: _FILTERED}


@pytest.mark.asyncio
async def test_the_result_reports_the_filtered_size(site: _Site) -> None:
    result = await _sync(WDKSyncState(wdk_step_ids={_STEP: _WDK_STEP_ID}))

    assert result.counts == {_STEP: _FILTERED}
    assert result.root_count == _FILTERED
