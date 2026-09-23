"""A snapshot is pushed to WDK as a strategy of its own, never re-used."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.strategy import StrategyAst

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.platform.errors import AppError, ErrorCode
from pathfinder.services.strategies import materialize
from pathfinder.services.strategies.materialize import materialize_strategy_snapshot
from pathfinder.services.strategies.step_push_planner import CreateAction, StepPushPlan
from pathfinder.services.strategies.step_wdk_push import PushOutcome
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.integration.persistence._strategy_shapes import three_step_ast

_SOURCE_IDS = {"combine": 15, "protease": 13, "gameto": 14}
_FRESH_IDS = {"combine": 7000, "protease": 7001, "gameto": 7002}


class _RecordingPush:
    def __init__(self) -> None:
        self.plans: list[list[StepPushPlan]] = []
        self.seen_existing_ids: list[dict[str, int]] = []

    async def __call__(
        self,
        graph: StrategyGraph,
        sync_state: WDKSyncState,
        site_id: str,
        plan: list[StepPushPlan],
    ) -> PushOutcome:
        del graph, site_id
        self.plans.append(plan)
        self.seen_existing_ids.append(dict(sync_state.wdk_step_ids))
        sync_state.wdk_step_ids.update(_FRESH_IDS)
        return PushOutcome(succeeded=sorted(_FRESH_IDS), failures=[])


async def _fake_sync(**kwargs: Any) -> SyncResult:
    del kwargs
    return SyncResult(
        wdk_strategy_id=330534153,
        wdk_url="https://plasmodb.org/plasmo/app/workspace/strategies/330534153",
        root_step_id=7000,
        counts={},
        root_count=0,
        zero_step_ids=[],
        step_count=3,
    )


async def test_the_snapshot_is_pushed_with_no_wdk_ids_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    push = _RecordingPush()
    monkeypatch.setattr(materialize, "push_steps_with_plan", push)
    monkeypatch.setattr(materialize, "sync_strategy_for_site", _fake_sync)
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

    assert push.seen_existing_ids == [{}]
    assert [type(entry.action) for entry in push.plans[0]] == [CreateAction] * 3
    assert result.wdk_strategy_id == 330534153
    assert result.step_count == 3
    pushed = TypeAdapter(dict[str, int]).validate_python(
        result.strategy_ast["wdkStepIds"]
    )
    assert pushed == _FRESH_IDS
    assert set(pushed.values()).isdisjoint(_SOURCE_IDS.values())


async def test_the_pushed_snapshot_names_its_combine_by_its_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(materialize, "push_steps_with_plan", _RecordingPush())
    monkeypatch.setattr(materialize, "sync_strategy_for_site", _fake_sync)

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
    async def _failing_push(*args: Any, **kwargs: Any) -> PushOutcome:
        del args, kwargs
        raise AppError(code=ErrorCode.WDK_ERROR, title="boom")

    monkeypatch.setattr(materialize, "push_steps_with_plan", _failing_push)
    monkeypatch.setattr(materialize, "sync_strategy_for_site", _fake_sync)
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
    push = _RecordingPush()
    monkeypatch.setattr(materialize, "push_steps_with_plan", push)

    result = await materialize_strategy_snapshot(
        site_id="plasmodb",
        conversation_id=uuid4(),
        name="empty",
        strategy_ast={},
    )

    assert push.plans == []
    assert result.wdk_strategy_id is None
    assert result.step_count == 0
