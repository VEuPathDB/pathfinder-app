from __future__ import annotations

import pytest
from veupathdb.domain.strategy import StrategyAst
from veupathdb.wdk import build_wdk_step_tree

from pathfinder.domain.strategy.operations import DeleteResolution, DeleteStepOp
from pathfinder.persistence.models import PersistedStrategyGraph
from pathfinder.services.strategies import commit, reconcile, sync
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.reconcile import reconcile_sync_state_with_wdk
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_IDS = {"step_a": 440537303, "step_b": 440537313, "step_join": 440537323}
_JOINED = "Combine transcript results for intersect."
_LEAF_A = "Find transcript results for GenesByTaxon."


async def _sync(
    monkeypatch: pytest.MonkeyPatch, state: WDKSyncState, stated: str | None = None
) -> StubAPI:
    api = StubAPI()
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site: api)
    session = session_with(combine("step_join", leaf("step_a"), leaf("step_b")), _IDS)
    assert session.graph is not None
    session.graph.description = stated
    for step in session.graph.steps.values():
        step.record_class = "transcript"
    await sync.sync_strategy_for_site(
        graph=session.graph, sync_state=state, site_id="plasmodb", strategy_name="G"
    )
    return api


def _pushed(held: str | None) -> WDKSyncState:
    root = combine("step_join", leaf("step_a"), leaf("step_b"))
    return WDKSyncState(
        wdk_step_ids=dict(_IDS),
        wdk_strategy_id=42,
        wdk_step_tree=build_wdk_step_tree(root, _IDS),
        wdk_strategy_name="G",
        wdk_strategy_description=held,
    )


def _label_writes(api: StubAPI) -> list[tuple[object, object, object]]:
    return [
        (c.kwargs["step_tree"], c.kwargs["name"], c.kwargs["description"])
        for c in api.named("update_strategy")
    ]


async def test_a_created_strategy_carries_the_description_its_root_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = WDKSyncState(wdk_step_ids=dict(_IDS))

    api = await _sync(monkeypatch, state)

    assert [c.kwargs["description"] for c in api.named("create_strategy")] == [_JOINED]
    assert state.wdk_strategy_description == _JOINED


async def test_a_description_wdk_lags_on_is_sent_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _pushed("")

    api = await _sync(monkeypatch, state)

    assert _label_writes(api) == [(None, None, _JOINED)]
    assert state.wdk_strategy_description == _JOINED


async def test_a_description_wdk_holds_sends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await _sync(monkeypatch, _pushed(_JOINED))

    assert api.calls == []


async def test_a_stated_description_is_the_one_wdk_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await _sync(monkeypatch, _pushed(_JOINED), stated="Apicoplast screen")

    assert _label_writes(api) == [(None, None, "Apicoplast screen")]


async def test_the_read_before_a_push_records_the_description_wdk_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = StubAPI()
    monkeypatch.setattr(reconcile, "get_strategy_api", lambda _site: api)
    state = WDKSyncState(wdk_step_ids={"step_a": 1}, wdk_strategy_id=42)

    await reconcile_sync_state_with_wdk(state, "plasmodb", 42)

    assert state.wdk_strategy_description == ""


async def test_a_delete_puts_the_tree_with_the_description_it_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = install_stub_api(monkeypatch)
    monkeypatch.setattr(commit, "sync_strategy_for_site", sync.sync_strategy_for_site)

    async def _no_marks(*_args: object) -> dict[str, str]:
        return {}

    monkeypatch.setattr(sync, "tree_organism_parameters", _no_marks)
    root = combine("step_join", leaf("step_a"), leaf("step_b"))
    session = session_with(root, dict(_IDS))
    state = ensure_sync_state(session)
    state.wdk_step_tree = build_wdk_step_tree(root, _IDS)
    state.wdk_strategy_description = _JOINED
    assert session.graph is not None
    for step in session.graph.steps.values():
        step.record_class = "transcript"

    await apply_and_commit(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        op=DeleteStepOp(step_id="step_b", resolution=DeleteResolution.COLLAPSE_COMBINE),
    )

    assert [
        (c.kwargs["step_tree"].step_id, c.kwargs["description"])
        for c in api.named("update_strategy")
    ] == [(_IDS["step_a"], _LEAF_A)]


def test_a_stored_derived_description_is_read_again_from_the_tree() -> None:
    root = leaf("step_a")
    stored = StrategyAst(
        record_type="transcript",
        root=root,
        description="Combine transcript results for intersect.",
    )

    session = build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(
            id="g1", name="G", strategy_ast=stored, wdk_strategy_id=None
        ),
    )

    assert session.graph is not None
    assert (session.graph.name, session.graph.description) == ("G", None)
