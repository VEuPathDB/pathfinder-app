"""WDK holds the name the graph carries, and a push sends it when WDK lags.

The name WDK holds is read with the strategy before every push, so a rename
WDK did not take is sent again by the next push.
"""

from __future__ import annotations

import pytest
from veupathdb.wdk import build_wdk_step_tree

from pathfinder.domain.strategy.operations import UpdateStrategyMetaOp
from pathfinder.services.strategies import reconcile, sync
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.reconcile import reconcile_sync_state_with_wdk
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_WDK_STRATEGY = 42
_IDS = {"step_a": 440537303, "step_b": 440537313, "step_join": 440537323}


def _name_writes(api: StubAPI) -> list[tuple[object, object]]:
    return [
        (call.kwargs["step_tree"], call.kwargs["name"])
        for call in api.named("update_strategy")
    ]


async def test_the_read_before_a_push_records_the_name_wdk_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = StubAPI()
    monkeypatch.setattr(reconcile, "get_strategy_api", lambda _site: api)
    state = WDKSyncState(wdk_step_ids={"step_a": 1}, wdk_strategy_id=_WDK_STRATEGY)

    await reconcile_sync_state_with_wdk(state, "plasmodb", _WDK_STRATEGY)

    assert state.wdk_strategy_name == "Test"


async def _sync(
    monkeypatch: pytest.MonkeyPatch, state: WDKSyncState, name: str
) -> StubAPI:
    """Sync the two-search join under ``name`` against a recording WDK."""
    api = StubAPI()
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site: api)
    session = session_with(combine("step_join", leaf("step_a"), leaf("step_b")), _IDS)
    assert session.graph is not None
    for step in session.graph.steps.values():
        step.record_class = "transcript"
    await sync.sync_strategy_for_site(
        graph=session.graph, sync_state=state, site_id="plasmodb", strategy_name=name
    )
    return api


def _pushed(held_name: str | None) -> WDKSyncState:
    """The state of a strategy WDK already holds with this tree."""
    root = combine("step_join", leaf("step_a"), leaf("step_b"))
    return WDKSyncState(
        wdk_step_ids=dict(_IDS),
        wdk_strategy_id=_WDK_STRATEGY,
        wdk_step_tree=build_wdk_step_tree(root, _IDS),
        wdk_strategy_name=held_name,
    )


class TestAnUnchangedTree:
    async def test_a_name_wdk_lags_on_is_sent_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = _pushed("New Conversation")

        api = await _sync(monkeypatch, state, "Kinase hunt")

        assert _name_writes(api) == [(None, "Kinase hunt")]
        assert state.wdk_strategy_name == "Kinase hunt"

    async def test_a_name_wdk_holds_sends_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = await _sync(monkeypatch, _pushed("Kinase hunt"), "Kinase hunt")

        assert api.calls == []

    async def test_a_name_nobody_read_sends_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = await _sync(monkeypatch, _pushed(None), "Kinase hunt")

        assert api.calls == []


async def test_a_created_strategy_records_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = WDKSyncState(wdk_step_ids=dict(_IDS))

    api = await _sync(monkeypatch, state, "Kinase hunt")

    assert [call.kwargs["name"] for call in api.named("create_strategy")] == [
        "Kinase hunt"
    ]
    assert state.wdk_strategy_name == "Kinase hunt"


async def test_a_renamed_strategy_sends_the_name_without_a_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = install_stub_api(monkeypatch)
    root = combine("step_join", leaf("step_a"), leaf("step_b"))
    session = session_with(root, dict(_IDS))
    state = ensure_sync_state(session)
    state.wdk_step_tree = build_wdk_step_tree(root, _IDS)
    state.wdk_strategy_name = "New Conversation"
    assert session.graph is not None
    session.graph.steps["step_join"].display_name = "Intersect"

    await apply_and_commit(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        op=UpdateStrategyMetaOp(name="Kinase hunt"),
    )

    assert _name_writes(api) == [(None, "Kinase hunt")]
    assert (session.graph.name, state.wdk_strategy_name) == (
        "Kinase hunt",
        "Kinase hunt",
    )
