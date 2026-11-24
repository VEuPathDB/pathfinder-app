from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import (
    StepFilter,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ValidatedParams

from strategist.ai.lead import sub_agent_dispatch
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.domain.strategy.operations import ReplaceSubtreeOp, UpdateStrategyMetaOp
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import commit_tree
from strategist.services.strategies.commit_tree import CommitTarget, CommittedTree
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from strategist.tests._support.held_steps import (
    LEAF_DEFAULT,
)
from strategist.tests._support.holding_wdk import (
    tree_ids,
)
from strategist.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    commit_ops,
    new_thread,
    node_of,
    plan_root,
    replace_with,
)

_PLAN_N = {"name": "matched_transcript_filter_array", "value": {"values": ["N"]}}


def _graph(root: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    return graph


async def _commit(
    graph: StrategyGraph, sync_state: WDKSyncState, old: StrategyAst | None
) -> CommittedTree:
    return await commit_tree.commit_tree(
        site_id="plasmodb",
        steps=graph.steps,
        root_id="step_root",
        old=old,
        sync_state=sync_state,
        target=CommitTarget(name="Kinases", description=""),
    )


def _held_filters(env: Env, sync_state: WDKSyncState, step_id: str) -> Any:
    return env.wdk.steps[sync_state.wdk_step_ids[step_id]]["searchConfig"]["filters"]


@pytest.mark.parametrize("refused", ["step read", "search-config put"])
async def test_a_step_whose_filters_did_not_land_is_finished_by_the_next_commit(
    monkeypatch: pytest.MonkeyPatch, refused: str
) -> None:
    env = Env(monkeypatch)
    graph = _graph(plan_root())
    sync_state = WDKSyncState()
    env.wdk.refuses_once = {refused}

    first = await _commit(graph, sync_state, None)
    second = await _commit(graph, sync_state, graph.to_strategy_ast())

    assert [f.step_id for f in first.failures] == ["step_a"]
    assert (first.sync, second.failures) == (None, [])
    assert second.sync is not None
    assert _held_filters(env, sync_state, "step_a") == [{**_PLAN_N, "disabled": False}]
    assert graph.steps["step_a"].filters_wdk_added == [
        StepFilter.model_validate(LEAF_DEFAULT)
    ]


async def _held_tree(env: Env, sync_state: WDKSyncState) -> StrategyGraph:
    graph = _graph(plan_root())
    await _commit(graph, sync_state, None)
    env.wdk.writes.clear()
    return graph


def _researched(graph: StrategyGraph) -> StrategyAst:
    before = graph.to_strategy_ast()
    assert before is not None
    graph.steps["step_a"].search_name = "GenesByOtherText"
    return before


async def test_a_recreate_whose_filters_did_not_land_deletes_the_step_it_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    sync_state = WDKSyncState()
    graph = await _held_tree(env, sync_state)
    replaced = sync_state.wdk_step_ids["step_a"]
    env.wdk.refuses_once = {"search-config put"}

    first = await _commit(graph, sync_state, _researched(graph))
    second = await _commit(graph, sync_state, graph.to_strategy_ast())

    assert ([f.step_id for f in first.failures], second.failures) == (["step_a"], [])
    assert replaced not in env.wdk.steps
    assert sync_state.replaced_wdk_step_ids == []


async def test_a_recreate_beside_a_refused_step_is_deleted_after_the_next_put(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    sync_state = WDKSyncState()
    graph = await _held_tree(env, sync_state)
    replaced = sync_state.wdk_step_ids["step_a"]
    before = _researched(graph)
    graph.steps["step_b"].search_name = "GenesByThirdText"
    env.wdk.refuses_once = {"step read"}

    first = await _commit(graph, sync_state, before)
    queued = list(sync_state.replaced_wdk_step_ids)
    await _commit(graph, sync_state, graph.to_strategy_ast())

    assert first.sync is None
    assert replaced in queued
    assert (replaced in env.wdk.steps, sync_state.replaced_wdk_step_ids) == (False, [])


async def test_a_resync_states_every_value_of_a_step_the_site_lacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)
    stated: list[dict[str, ParamValue]] = []

    async def _recorded(*_args: object, **kwargs: Any) -> ValidatedParams:
        stated.append(dict(kwargs["stated"]))
        return ValidatedParams(params=dict(kwargs["stated"]))

    monkeypatch.setattr(commit_tree, "validate_parameters", _recorded)
    session = session_with_one_step()
    assert session.graph is not None
    words = {"text_expression": StringValue(value="kinase")}
    session.graph.steps["step_a"].parameters = dict(words)
    deps = lead_deps(pipeline_state(user_prompt="kinases"), strategy_session=session)

    await sub_agent_dispatch._resync_outcome(
        agent_deps_for(deps, call_id="call_test"), BuildOutcome()
    )

    assert stated == [words]


async def test_a_resync_that_leaves_a_draft_reports_it_and_no_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)

    async def _refused(*_args: object, **_kwargs: object) -> ValidatedParams:
        raise ValidationError(title="text_expression is required")

    monkeypatch.setattr(commit_tree, "validate_parameters", _refused)
    session = session_with_one_step()
    ensure_sync_state(session).wdk_strategy_id = 41
    deps = lead_deps(pipeline_state(user_prompt="kinases"), strategy_session=session)

    outcome = await sub_agent_dispatch._resync_outcome(
        agent_deps_for(deps, call_id="call_test"), BuildOutcome()
    )

    assert [f.step_id for f in outcome.failed_steps] == ["step_a"]
    assert outcome.wdk_strategy_id is None


async def test_a_step_a_stopped_commit_made_is_kept_by_the_next_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    sync_state = ensure_sync_state(deps.strategy_session)
    researched = node_of(plan_root(), "step_a").model_copy(
        update={"search_name": "GenesByOtherText"}
    )
    env.wdk.refuses_once = {"step read"}

    await commit_ops(deps, ReplaceSubtreeOp(step_id="step_a", subtree=researched))
    made = sync_state.wdk_step_ids["step_a"]
    await commit_ops(deps, UpdateStrategyMetaOp(description="Kinases again"))

    (strategy,) = env.wdk.strategies.values()
    assert sync_state.wdk_step_ids["step_a"] == made
    assert set(env.wdk.steps) == set(tree_ids(strategy["stepTree"]))
