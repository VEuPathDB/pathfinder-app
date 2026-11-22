"""A snapshot is pushed to WDK as a strategy of its own, never re-used."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.strategy import StrategyAst

from strategist.platform.errors import AppError, ErrorCode
from strategist.services.strategies import materialize
from strategist.services.strategies.materialize import materialize_strategy_snapshot
from strategist.tests.integration.persistence._strategy_shapes import three_step_ast
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
)

_SOURCE_IDS = {"combine": 15, "protease": 13, "gameto": 14}


async def test_the_snapshot_is_pushed_with_no_wdk_ids_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    snapshot = three_step_ast(dict(_SOURCE_IDS)).model_dump(
        by_alias=True,
        exclude_none=True,
        mode="json",
    )

    result = await materialize_strategy_snapshot(
        site_id="plasmodb",
        conversation_id=uuid4(),
        name="protease work",
        strategy_ast=snapshot,
    )

    assert [w.method for w in env.wdk.written("POST", "/steps")] == ["POST"] * 3
    assert result.wdk_strategy_id in env.wdk.strategies
    assert result.step_count == 3
    pushed = TypeAdapter(dict[str, int]).validate_python(
        result.strategy_ast["wdkStepIds"]
    )
    assert sorted(pushed) == sorted(_SOURCE_IDS)
    assert set(pushed.values()) == set(env.wdk.steps)


async def test_the_pushed_snapshot_names_its_combine_by_its_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)

    result = await materialize_strategy_snapshot(
        site_id="plasmodb",
        conversation_id=uuid4(),
        name="protease work",
        strategy_ast=three_step_ast().model_dump(
            by_alias=True, exclude_none=True, mode="json"
        ),
    )

    pushed = StrategyAst.model_validate(result.strategy_ast)
    assert pushed.root.display_name == "Intersect"


async def test_a_wdk_failure_leaves_the_thread_with_the_plan_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _failing(**kwargs: Any) -> None:
        del kwargs
        raise AppError(code=ErrorCode.WDK_ERROR, title="boom")

    monkeypatch.setattr(materialize, "commit_tree", _failing)
    snapshot = three_step_ast(dict(_SOURCE_IDS)).model_dump(
        by_alias=True,
        exclude_none=True,
        mode="json",
    )

    result = await materialize_strategy_snapshot(
        site_id="plasmodb",
        conversation_id=uuid4(),
        name="protease work",
        strategy_ast=snapshot,
    )

    assert result.wdk_strategy_id is None
    assert "wdkStepIds" not in result.strategy_ast
    assert result.step_count == 3


async def test_a_snapshot_with_no_tree_materializes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)

    result = await materialize_strategy_snapshot(
        site_id="plasmodb",
        conversation_id=uuid4(),
        name="empty",
        strategy_ast={},
    )

    assert env.wdk.writes == []
    assert result.wdk_strategy_id is None
    assert result.step_count == 0
