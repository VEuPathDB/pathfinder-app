"""The sync reports whether it minted the WDK strategy it returns.

Only a minted strategy is PathFinder's to delete, so the flag is true on
exactly the branches that call ``create_strategy``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    SiteInfo,
    StrategyAPI,
    WDKIdentifier,
    WDKStepTree,
    WDKStrategyDetails,
)

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import sync
from pathfinder.services.strategies.sync import SyncResult, sync_strategy_for_site
from pathfinder.services.strategies.sync_state import WDKSyncState

_WDK_STEP_ID = 1001
_ADOPTED_ID = 42
_MINTED_ID = 777
_SITE = SiteInfo(
    id="plasmodb",
    name="plasmodb",
    display_name="PlasmoDB",
    base_url="https://plasmodb.org/plasmo/service",
    project_id="PlasmoDB",
    is_portal=False,
)


def _details(strategy_id: int) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": strategy_id,
            "rootStepId": _WDK_STEP_ID,
            "name": "test",
            "stepTree": {"stepId": _WDK_STEP_ID},
            "steps": {
                str(_WDK_STEP_ID): {
                    "id": _WDK_STEP_ID,
                    "searchName": "GenesByMolecularWeight",
                    "searchConfig": {"parameters": {}},
                    "estimatedSize": 5,
                }
            },
            "recordClassName": "transcript",
        }
    )


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Mock:
    stub = Mock(spec=StrategyAPI)

    async def create_strategy(*_args: object, **_kwargs: object) -> WDKIdentifier:
        return WDKIdentifier(id=_MINTED_ID)

    async def get_strategy(*_args: object, **_kwargs: object) -> WDKStrategyDetails:
        return _details(_ADOPTED_ID)

    stub.create_strategy = AsyncMock(side_effect=create_strategy)
    stub.get_strategy = AsyncMock(side_effect=get_strategy)
    stub.update_strategy = AsyncMock(return_value=None)
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: stub)
    monkeypatch.setattr(sync, "get_site", lambda _site_id: _SITE)
    return stub


def _graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "test", "plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(id="A", search_name="GenesByMolecularWeight")
    )
    graph.steps["A"].record_class = "transcript"
    graph.record_type = "transcript"
    graph.recompute_roots()
    return graph


async def _sync(sync_state: WDKSyncState) -> SyncResult:
    return await sync_strategy_for_site(
        graph=_graph(),
        sync_state=sync_state,
        site_id="plasmodb",
    )


def _adopted(step_tree: WDKStepTree | None) -> WDKSyncState:
    return WDKSyncState(
        wdk_step_ids={"A": _WDK_STEP_ID},
        wdk_strategy_id=_ADOPTED_ID,
        wdk_step_tree=step_tree,
    )


@pytest.mark.asyncio
async def test_a_thread_with_no_strategy_yet_mints_one(api: Mock) -> None:
    result = await _sync(WDKSyncState(wdk_step_ids={"A": _WDK_STEP_ID}))

    assert (result.wdk_strategy_id, result.created_wdk_strategy) == (_MINTED_ID, True)


@pytest.mark.asyncio
async def test_an_update_of_an_existing_strategy_mints_nothing(api: Mock) -> None:
    result = await _sync(_adopted(WDKStepTree(step_id=9999)))

    assert (result.wdk_strategy_id, result.created_wdk_strategy) == (_ADOPTED_ID, False)
    assert api.update_strategy.await_count == 1


@pytest.mark.asyncio
async def test_a_refused_update_mints_a_replacement(api: Mock) -> None:
    api.update_strategy = AsyncMock(side_effect=WDKError("refused", status=500))

    result = await _sync(_adopted(WDKStepTree(step_id=9999)))

    assert (result.wdk_strategy_id, result.created_wdk_strategy) == (_MINTED_ID, True)


@pytest.mark.asyncio
async def test_an_unchanged_tree_mints_nothing(api: Mock) -> None:
    result = await _sync(_adopted(WDKStepTree(step_id=_WDK_STEP_ID)))

    assert (result.wdk_strategy_id, result.created_wdk_strategy) == (_ADOPTED_ID, False)
    assert api.create_strategy.await_count == 0
