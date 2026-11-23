from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StepFilter, StrategyAst, flatten_tree
from veupathdb.wdk import tag_internal_wdk_strategy_name

from strategist.domain.strategy.operations import (
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
)
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies.commit_tree import (
    CommitTarget,
    CommittedTree,
    commit_tree,
)
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from strategist.tests.unit.services.strategies._holding_strategy_api import (
    LEAF_DEFAULT,
)
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    commit_ops,
    new_thread,
    node_of,
    plan_root,
    replace_with,
)

_FILTER = "matched_transcript_filter_array"
_DEFAULT = StepFilter.model_validate(LEAF_DEFAULT)
_UNION_DEFAULT = StepFilter(
    name="gene_boolean_filter_array", value={"values": ["YY", "YN", "NY"]}
)
_INTERSECT_DEFAULT = StepFilter(
    name="gene_boolean_filter_array", value={"values": ["YY"]}
)


async def _commit_thread(
    graph: StrategyGraph, sync_state: WDKSyncState, old: StrategyAst | None
) -> CommittedTree:
    return await commit_tree(
        site_id="plasmodb",
        steps=graph.steps,
        root_id="step_root",
        old=old,
        sync_state=sync_state,
        target=CommitTarget(name="Kinases", description=""),
    )


def _added(deps: StrategyMutationContext) -> dict[str, list[StepFilter] | None]:
    graph = deps.strategy_session.graph
    assert graph is not None
    return {sid: step.filters_wdk_added for sid, step in graph.steps.items()}


async def test_a_step_is_created_bare_and_then_given_its_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()

    await commit_ops(deps, replace_with(plan_root()))

    a_id = ensure_sync_state(deps.strategy_session).wdk_step_ids["step_a"]
    (create,) = [
        w
        for w in env.wdk.written("POST", "/steps")
        if w.body["customName"] == "Kinase text"
    ]
    assert "filters" not in create.body["searchConfig"]
    (put,) = env.wdk.written("PUT", f"/steps/{a_id}/search-config")
    assert put.body["filters"] == [
        {"name": _FILTER, "value": {"values": ["N"]}, "disabled": False}
    ]
    added = _added(deps)
    assert added["step_a"] == [_DEFAULT]
    assert added["step_union"] == [_UNION_DEFAULT]


async def test_a_recreated_combine_learns_what_wdk_adds_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))

    await commit_ops(
        deps,
        UpdateCombineOperatorOp(step_id="step_union", operator=CombineOp.INTERSECT),
    )

    added = _added(deps)
    assert added["step_union"] == [_INTERSECT_DEFAULT]


async def test_a_removed_plan_filter_the_site_resets_is_not_a_departure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    unfiltered = plan_root()
    node_of(unfiltered, "step_a").filters = []

    await commit_ops(
        deps, ReplaceSubtreeOp(step_id="step_a", subtree=node_of(unfiltered, "step_a"))
    )

    assert ensure_sync_state(deps.strategy_session).wdk_push_errors == {}
    a_id = ensure_sync_state(deps.strategy_session).wdk_step_ids["step_a"]
    assert env.wdk.steps[a_id]["searchConfig"]["filters"] == [LEAF_DEFAULT]


@pytest.mark.parametrize(
    ("role", "saved", "name"),
    [
        ("saved", True, "Kinases"),
        ("internal", False, tag_internal_wdk_strategy_name("Kinases")),
    ],
)
async def test_a_saved_or_internal_tree_is_a_new_strategy(
    monkeypatch: pytest.MonkeyPatch, role: str, saved: bool, name: str
) -> None:
    env = Env(monkeypatch)
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.steps = flatten_tree(plan_root())
    graph.recompute_roots()

    committed = await commit_tree(
        site_id="plasmodb",
        steps=graph.steps,
        root_id="step_root",
        old=None,
        sync_state=WDKSyncState(),
        target=CommitTarget.model_validate(
            {"name": "Kinases", "description": "", "role": role}
        ),
    )

    assert committed.sync is not None
    held = env.wdk.strategies[committed.sync.wdk_strategy_id or 0]
    assert (held["isSaved"], held["name"]) == (saved, name)
    assert name.startswith("Kinases") is (role == "saved")


async def test_a_saved_tree_needs_a_fresh_sync_state() -> None:
    with pytest.raises(ValueError, match="fresh sync state"):
        await commit_tree(
            site_id="plasmodb",
            steps=flatten_tree(plan_root()),
            root_id="step_root",
            old=None,
            sync_state=WDKSyncState(wdk_strategy_id=7),
            target=CommitTarget(name="Kinases", description="", role="saved"),
        )


async def test_an_imported_step_learns_what_wdk_added_from_the_read_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    graph = deps.strategy_session.graph
    assert graph is not None
    for step in graph.steps.values():
        step.filters_wdk_added = None
    unfiltered = plan_root()
    node_of(unfiltered, "step_a").filters = []

    await commit_ops(
        deps, ReplaceSubtreeOp(step_id="step_a", subtree=node_of(unfiltered, "step_a"))
    )

    assert ensure_sync_state(deps.strategy_session).wdk_push_errors == {}
    assert graph.steps["step_a"].filters_wdk_added == [_DEFAULT]


async def test_a_default_wdk_puts_back_on_an_imported_step_is_recorded_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)
    sync_state = WDKSyncState()
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.steps = flatten_tree(plan_root(a_filter=("Y",)))
    graph.recompute_roots()
    await _commit_thread(graph, sync_state, None)
    graph.steps["step_a"].filters_wdk_added = None
    before = graph.to_strategy_ast()
    graph.steps["step_a"].filters = []

    out = await _commit_thread(graph, sync_state, before)

    recorded = {sid: s.filters_wdk_added for sid, s in graph.steps.items()}
    assert (out.failures, recorded["step_a"]) == ([], [_DEFAULT])


async def test_an_unrecorded_strategy_committed_unchanged_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    graph = deps.strategy_session.graph
    assert graph is not None
    ids = dict(ensure_sync_state(deps.strategy_session).wdk_step_ids)
    for step in graph.steps.values():
        step.filters_wdk_added = None
    written = len(env.wdk.writes)

    await commit_ops(deps, replace_with(plan_root()))

    step_writes = [w for w in env.wdk.writes[written:] if "/steps" in w.path]
    assert step_writes == []
    assert ensure_sync_state(deps.strategy_session).wdk_step_ids == ids
    assert _added(deps) == {
        "step_a": [],
        "step_b": [_DEFAULT],
        "step_union": [_UNION_DEFAULT],
        "step_c": [_DEFAULT],
        "step_coloc": [],
        "step_d": [_DEFAULT],
        "step_root": [_INTERSECT_DEFAULT],
    }
