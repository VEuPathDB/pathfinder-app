from __future__ import annotations

import pytest
from veupathdb.errors import WDKError

from strategist.domain.strategy.operations import DeleteStepOp, ReplaceSubtreeOp
from strategist.domain.strategy.operations.types import DeleteResolution
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    commit_ops,
    new_thread,
    node_of,
    plan_root,
    replace_with,
)


def _reweigh_a() -> ReplaceSubtreeOp:
    return ReplaceSubtreeOp(
        step_id="step_a", subtree=node_of(plan_root(a_weight=3), "step_a")
    )


@pytest.mark.parametrize(
    ("fault", "said"),
    [
        (
            "refuses_once",
            "PlasmoDB (Plasmodium) did not answer the read of the strategy",
        ),
        (
            "garbles_once",
            (
                "PlasmoDB (Plasmodium) answered the read of the strategy with a "
                "strategy that does not parse"
            ),
        ),
    ],
)
async def test_an_edit_after_a_failed_read_writes_nothing_until_the_next_commit(
    monkeypatch: pytest.MonkeyPatch, fault: str, said: str
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    sync_state = ensure_sync_state(deps.strategy_session)
    a_id = sync_state.wdk_step_ids["step_a"]
    getattr(env.wdk, fault).add("strategy read")
    written = len(env.wdk.writes)

    failed = await apply_operations_and_commit(deps=deps, ops=[_reweigh_a()])

    assert env.wdk.writes[written:] == []
    assert [f.error.startswith(said) for f in failed.failures] == [True]

    await commit_ops(deps, _reweigh_a())

    assert env.wdk.steps[a_id]["searchConfig"]["wdkWeight"] == 3
    assert sync_state.wdk_push_errors == {}


async def test_a_clear_after_a_refused_read_restores_the_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    graph = deps.strategy_session.graph
    assert graph is not None
    before = set(graph.steps)
    env.wdk.refuses_once.add("strategy read")
    written = len(env.wdk.writes)

    with pytest.raises(WDKError):
        await apply_operations_and_commit(
            deps=deps,
            ops=[
                DeleteStepOp(
                    step_id="step_root", resolution=DeleteResolution.DELETE_STRATEGY
                )
            ],
        )

    assert (set(graph.steps), env.wdk.writes[written:]) == (before, [])
