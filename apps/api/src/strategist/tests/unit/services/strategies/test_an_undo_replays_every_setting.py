from __future__ import annotations

from pathlib import Path

import pytest
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    FIELDS,
    Env,
    _patch_ops,
    _row,
    commit_ops,
    new_thread,
    node_of,
    plan_root,
    replace_with,
)

_UNDO_PLAN = (
    Path(__file__).resolve().parents[7]
    / "web/src/features/strategy/graph/__fixtures__/undo-plan.json"
)


def _replayed(root: StrategyStepNode) -> StrategyStepNode:
    undo = StrategyAst.model_validate_json(_UNDO_PLAN.read_text()).root
    node_of(undo, "step_a").filters = list(node_of(root, "step_a").filters)
    return undo


async def test_p1_undo_replay_holds_every_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    await commit_ops(deps, *_patch_ops())

    async def write(root: StrategyStepNode) -> int | None:
        return await commit_ops(deps, replace_with(_replayed(root)))

    assert await _row(env, plan_root(), write) == FIELDS
