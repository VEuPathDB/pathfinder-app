"""The commit reports whether it minted the WDK strategy it returns.

Only a minted strategy is Strategist's to delete, so the flag is true on
exactly the branches that call ``create_strategy``.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree

from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies.commit_tree import CommittedTree
from strategist.services.strategies.sync import SyncResult
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.recording_wdk import RecordingWDK
from strategist.tests._support.wdk_write_stubs import put_the_graph, serve_the_site

_WDK_STEP_ID = 1001
_OTHER_STEP_ID = 9999
_ADOPTED_ID = 42


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> RecordingWDK:
    wdk = RecordingWDK()
    serve_the_site(monkeypatch, wdk)
    return wdk


def _graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "test", "plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(id="A", search_name="GenesByMolecularWeight")
    )
    graph.steps["A"].record_class = "transcript"
    graph.record_type = "transcript"
    graph.recompute_roots()
    return graph


def _held(api: RecordingWDK, sync_state: WDKSyncState) -> WDKSyncState:
    api.holds(_graph().steps, WDKSyncState(wdk_step_ids={"A": _WDK_STEP_ID}))
    return sync_state


def _adopted(api: RecordingWDK, *, root: int) -> WDKSyncState:
    api.wdk.holds_the_strategy(
        {
            "strategyId": _ADOPTED_ID,
            "name": "test",
            "stepTree": {"stepId": root},
            "steps": {
                str(root): {
                    "searchName": "GenesByMolecularWeight",
                    "searchConfig": {"parameters": {}},
                }
            },
        }
    )
    return _held(
        api,
        WDKSyncState(
            wdk_step_ids={"A": _WDK_STEP_ID},
            wdk_strategy_id=_ADOPTED_ID,
            wdk_step_tree=WDKStepTree(step_id=root),
        ),
    )


async def _commit(sync_state: WDKSyncState) -> CommittedTree:
    return await put_the_graph(_graph(), sync_state, "plasmodb")


async def _sync(sync_state: WDKSyncState) -> SyncResult:
    result = (await _commit(sync_state)).sync
    assert result is not None
    return result


def _minted(api: RecordingWDK) -> list[int]:
    return [i for i in api.wdk.strategies if i != _ADOPTED_ID]


async def test_a_thread_with_no_strategy_yet_mints_one(api: RecordingWDK) -> None:
    result = await _sync(_held(api, WDKSyncState(wdk_step_ids={"A": _WDK_STEP_ID})))

    assert (
        [result.wdk_strategy_id],
        result.created_wdk_strategy,
        len(api.named("create_strategy")),
    ) == (_minted(api), True, 1)


async def test_an_update_of_an_existing_strategy_mints_nothing(
    api: RecordingWDK,
) -> None:
    result = await _sync(_adopted(api, root=_OTHER_STEP_ID))

    assert (result.wdk_strategy_id, result.created_wdk_strategy) == (_ADOPTED_ID, False)
    assert (len(api.named("update_strategy")), _minted(api)) == (1, [])


async def test_a_refused_update_mints_nothing(api: RecordingWDK) -> None:
    api.wdk.refuses_once.add("strategy tree put")
    state = _adopted(api, root=_OTHER_STEP_ID)

    committed = await _commit(state)

    assert [f.step_id for f in committed.failures] == ["A"]
    assert (state.wdk_strategy_id, api.named("create_strategy")) == (_ADOPTED_ID, [])


async def test_an_unchanged_tree_mints_nothing(api: RecordingWDK) -> None:
    state = _adopted(api, root=_WDK_STEP_ID)

    committed = await _commit(state)

    assert (committed.sync, state.wdk_strategy_id) == (None, _ADOPTED_ID)
    assert api.named("create_strategy") == []
