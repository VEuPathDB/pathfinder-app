"""A step is orphaned by the strategy push, so it is deleted after it.

WDK refuses to delete a step the stored strategy still references. Deleting
before the push guarantees the refusal, and dropping the local id anyway means
nothing knows the step exists to retry it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.errors import WDKError
from veupathdb.wdk.strategy_api.steps import StepsMixin
from veupathdb.wdk.wdk_models import NewStepSpec, WDKIdentifier

from pathfinder.domain.strategy.operations import DeleteResolution, DeleteStepOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import commit, step_wdk_push
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState

_STILL_REFERENCED = "409: step belongs to a strategy"


@dataclass
class _Recorder:
    """Records the order of the WDK calls a commit makes."""

    order: list[str] = field(default_factory=list)
    refuse: set[int] = field(default_factory=set)
    next_id: int = 9000

    delete_orphaned_steps = StepsMixin.delete_orphaned_steps

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self.order.append(f"delete:{step_id}")
        if step_id in self.refuse:
            raise WDKError(_STILL_REFERENCED, status=409)

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del spec, record_type, user_id
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def create_combined_step(self, **_kwargs: Any) -> WDKIdentifier:
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def create_transform_step(self, **_kwargs: Any) -> WDKIdentifier:
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def update_step_search_config(self, **_kwargs: Any) -> None:
        return None


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    api = _Recorder()
    monkeypatch.setattr(commit, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: api)

    async def _no_validate(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    async def _no_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def _sync(**kwargs: Any) -> SyncResult:
        del kwargs
        api.order.append("sync")
        return SyncResult(
            wdk_strategy_id=42,
            wdk_url="http://example.invalid",
            root_step_id=0,
            counts={},
            root_count=None,
            zero_step_ids=[],
            step_count=0,
        )

    async def _no_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _no_validate)
    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _no_reconcile)
    monkeypatch.setattr(commit, "sync_strategy_for_site", _sync)
    monkeypatch.setattr(commit, "persist_strategy_ast_to_conversation", _no_persist)
    return api


def _deps(wdk_step_ids: dict[str, int]) -> StrategyMutationContext:
    a = StrategyStepNode(id="A", search_name="geneById")
    b = StrategyStepNode(id="B", search_name="geneById")
    root = StrategyStepNode(
        id="C",
        search_name="__combine__",
        primary_input=a,
        secondary_input=b,
        operator=CombineOp.INTERSECT,
    )
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Test", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids), wdk_strategy_id=42
    )
    return StrategyMutationContext(
        site_id="plasmodb", strategy_session=session, conversation_id=uuid4()
    )


async def _drop_a(deps: StrategyMutationContext) -> None:
    await apply_and_commit(
        deps=deps,
        op=DeleteStepOp(step_id="A", resolution=DeleteResolution.COLLAPSE_COMBINE),
    )


class TestTheDeleteFollowsThePush:
    @pytest.mark.asyncio
    async def test_the_strategy_is_pushed_before_any_delete(
        self, wdk: _Recorder
    ) -> None:
        await _drop_a(_deps({"A": 100, "B": 200, "C": 300}))

        deletes = [i for i, call in enumerate(wdk.order) if call.startswith("delete:")]
        assert wdk.order.index("sync") < min(deletes)

    @pytest.mark.asyncio
    async def test_both_orphans_are_still_deleted(self, wdk: _Recorder) -> None:
        await _drop_a(_deps({"A": 100, "B": 200, "C": 300}))

        assert {c for c in wdk.order if c.startswith("delete:")} == {
            "delete:100",
            "delete:300",
        }


class TestARefusedDeleteIsRetryable:
    @pytest.mark.asyncio
    async def test_the_id_survives_for_the_next_commit(self, wdk: _Recorder) -> None:
        wdk.refuse = {100}
        deps = _deps({"A": 100, "B": 200, "C": 300})

        await _drop_a(deps)

        assert deps.strategy_session.sync_state.wdk_step_ids.get("A") == 100

    @pytest.mark.asyncio
    async def test_a_deleted_id_is_forgotten(self, wdk: _Recorder) -> None:
        wdk.refuse = {100}
        deps = _deps({"A": 100, "B": 200, "C": 300})

        await _drop_a(deps)

        assert "C" not in deps.strategy_session.sync_state.wdk_step_ids

    @pytest.mark.asyncio
    async def test_every_id_is_forgotten_when_wdk_accepts(self, wdk: _Recorder) -> None:
        deps = _deps({"A": 100, "B": 200, "C": 300})

        await _drop_a(deps)

        remaining = deps.strategy_session.sync_state.wdk_step_ids
        assert "A" not in remaining
        assert "C" not in remaining
