from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue

from strategist.ai.lead import sub_agent_dispatch
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.services.strategies.test_a_half_written_step_is_finished import (
    _commit,
    _held_tree,
    _researched,
)
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    commit_ops,
    new_thread,
    plan_root,
    replace_with,
)


async def test_a_value_whose_put_was_refused_is_written_by_the_next_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    sync_state = WDKSyncState()
    graph = await _held_tree(env, sync_state)
    before = graph.to_strategy_ast()
    graph.steps["step_b"].parameters = {"text_expression": StringValue(value="actin")}
    env.wdk.refuses_once = {"search-config put"}

    first = await _commit(graph, sync_state, before)
    second = await _commit(graph, sync_state, graph.to_strategy_ast())

    held = env.wdk.steps[sync_state.wdk_step_ids["step_b"]]["searchConfig"]
    assert [f.step_id for f in first.failures] == ["step_b"]
    assert (second.failures, second.drafts) == ([], {})
    assert held["parameters"]["text_expression"] == "actin"
    assert sync_state.wdk_push_errors == {}


async def test_a_search_whose_recreate_was_refused_is_recreated_by_the_next_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    sync_state = WDKSyncState()
    graph = await _held_tree(env, sync_state)
    replaced = sync_state.wdk_step_ids["step_a"]
    env.wdk.refuses_once = {"step create"}

    first = await _commit(graph, sync_state, _researched(graph))
    second = await _commit(graph, sync_state, graph.to_strategy_ast())

    held = env.wdk.steps[sync_state.wdk_step_ids["step_a"]]
    assert [f.step_id for f in first.failures] == ["step_a"]
    assert (second.failures, held["searchName"]) == ([], "GenesByOtherText")
    assert replaced not in env.wdk.steps


async def test_a_resync_after_a_refused_put_rewrites_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    session = deps.strategy_session
    sync_state = ensure_sync_state(session)
    graph = session.graph
    assert graph is not None
    step_b = sync_state.wdk_step_ids["step_b"]
    graph.steps["step_b"].parameters = {"text_expression": StringValue(value="actin")}
    env.wdk.refuses_once = {"search-config put"}
    await _commit(graph, sync_state, graph.to_strategy_ast())
    lead = lead_deps(pipeline_state(user_prompt="kinases"), strategy_session=session)

    await sub_agent_dispatch._resync_outcome(
        agent_deps_for(lead, call_id="call_test"), BuildOutcome()
    )

    held = env.wdk.steps[step_b]["searchConfig"]
    assert (
        sync_state.wdk_step_ids["step_b"],
        held["parameters"]["text_expression"],
    ) == (
        step_b,
        "actin",
    )
