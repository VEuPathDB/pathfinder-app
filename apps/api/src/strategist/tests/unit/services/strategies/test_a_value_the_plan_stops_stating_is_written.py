from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode

from strategist.domain.strategy.operations import ReplaceSubtreeOp
from strategist.services.strategies.spec_build import build_strategy_from_spec
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    commit_ops,
    new_thread,
    node_of,
    plan_root,
    replace_with,
)


def _b(**parameters: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_b",
        search_name="GenesByTextSearch",
        display_name="Rhoptry text",
        wdk_weight=5,
        parameters={name: StringValue(value=v) for name, v in parameters.items()},
    )


def _with_b(b: StrategyStepNode) -> StrategyStepNode:
    root = plan_root()
    union = node_of(root, "step_union")
    union.secondary_input = b
    return root


def _held_b(env: Env, b_wdk_id: int) -> dict[str, str]:
    held: dict[str, str] = env.wdk.steps[b_wdk_id]["searchConfig"]["parameters"]
    return held


async def test_an_edit_that_drops_a_value_writes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(
        deps,
        replace_with(_with_b(_b(text_expression="rhoptry", text_fields="product"))),
    )
    b_id = ensure_sync_state(deps.strategy_session).wdk_step_ids["step_b"]

    await commit_ops(
        deps, ReplaceSubtreeOp(step_id="step_b", subtree=_b(text_expression="rhoptry"))
    )

    assert _held_b(env, b_id) == {"text_expression": "rhoptry"}
    assert [w.path for w in env.wdk.written("PUT", "/search-config")][-1].endswith(
        f"/steps/{b_id}/search-config"
    )


async def test_a_build_that_drops_a_value_writes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await build_strategy_from_spec(
        deps=deps, root=_with_b(_b(text_expression="rhoptry", text_fields="product"))
    )
    b_id = ensure_sync_state(deps.strategy_session).wdk_step_ids["step_b"]

    await build_strategy_from_spec(
        deps=deps, root=_with_b(_b(text_expression="rhoptry"))
    )

    held = ensure_sync_state(deps.strategy_session).wdk_step_ids["step_b"]
    assert _held_b(env, held) == {"text_expression": "rhoptry"}
    assert held == b_id
