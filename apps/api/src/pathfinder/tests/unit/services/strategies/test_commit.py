from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.operations import (
    DeleteResolution,
    DeleteStepOp,
    UpdateStepMetaOp,
)
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.session import StrategyGraph, StrategySession
from veupathdb.wdk.strategy_api.steps import StepsMixin
from veupathdb.wdk.wdk_models import (
    NewStepSpec,
    PatchStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)

from pathfinder.services.strategies import commit, step_wdk_push, sync
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState


@dataclass
class _Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class _StubAPI:
    calls: list[_Call] = field(default_factory=list)
    next_id: int = 9000

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    delete_orphaned_steps = StepsMixin.delete_orphaned_steps

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self.calls.append(_Call("delete_step", {"step_id": step_id}))

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del spec, record_type, user_id
        return WDKIdentifier(id=self._alloc())

    async def create_combined_step(self, **_kwargs: Any) -> WDKIdentifier:
        return WDKIdentifier(id=self._alloc())

    async def create_transform_step(self, **_kwargs: Any) -> WDKIdentifier:
        return WDKIdentifier(id=self._alloc())

    async def update_step_search_config(self, **_kwargs: Any) -> None:
        return None

    async def update_step_properties(
        self, step_id: int, spec: PatchStepSpec, *, user_id: str | None = None
    ) -> None:
        del user_id
        self.calls.append(
            _Call("update_step_properties", {"step_id": step_id, "spec": spec})
        )

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByTaxon",
            search_config=WDKSearchConfig(parameters={}),
        )


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> _StubAPI:
    api = _StubAPI()
    monkeypatch.setattr(commit, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: api)

    async def _noop_validate(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _noop_validate)

    async def _noop_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _noop_reconcile)

    async def _fake_sync(
        *,
        graph: Any,
        sync_state: Any,
        site_id: str,
        strategy_name: str | None = None,
    ) -> SyncResult:
        del graph, sync_state, site_id, strategy_name
        return SyncResult(
            wdk_strategy_id=42,
            wdk_url="http://example",
            root_step_id=0,
            counts={},
            root_count=None,
            zero_step_ids=[],
            step_count=0,
        )

    monkeypatch.setattr(commit, "sync_strategy_for_site", _fake_sync)

    async def _noop_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "persist_strategy_ast_to_conversation", _noop_persist)

    return api


def _leaf(id_: str) -> StrategyStepNode:
    return StrategyStepNode(id=id_, search_name="geneById")


def _combine(id_: str, p: StrategyStepNode, s: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id=id_,
        search_name="__combine__",
        primary_input=p,
        secondary_input=s,
        operator=CombineOp.INTERSECT,
    )


def _seed_session(
    root: StrategyStepNode, wdk_step_ids: dict[str, int]
) -> StrategyMutationContext:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Test", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids),
        wdk_strategy_id=42,
    )
    return StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_delete_step_collapses_and_calls_wdk_delete(stub_api: _StubAPI) -> None:
    a = _leaf("A")
    b = _leaf("B")
    c = _combine("C", a, b)
    deps = _seed_session(c, wdk_step_ids={"A": 100, "B": 200, "C": 300})

    result = await apply_and_commit(
        deps=deps,
        op=DeleteStepOp(step_id="A", resolution=DeleteResolution.COLLAPSE_COMBINE),
    )

    graph = deps.strategy_session.graph
    assert graph is not None
    assert sorted(graph.steps.keys()) == ["B"]
    assert sorted(result.dropped_step_ids) == ["A", "C"]

    deleted_ids = {
        c.kwargs["step_id"] for c in stub_api.calls if c.name == "delete_step"
    }
    assert deleted_ids == {100, 300}
    assert "A" not in deps.strategy_session.sync_state.wdk_step_ids
    assert "C" not in deps.strategy_session.sync_state.wdk_step_ids


@pytest.mark.asyncio
async def test_update_step_meta_does_not_delete_wdk_steps(stub_api: _StubAPI) -> None:
    a = _leaf("a")
    deps = _seed_session(a, wdk_step_ids={"a": 100})

    await apply_and_commit(
        deps=deps,
        op=UpdateStepMetaOp(step_id="a", display_name="renamed"),
    )

    assert deps.strategy_session.graph is not None
    assert deps.strategy_session.graph.steps["a"].display_name == "renamed"
    deletes = [c for c in stub_api.calls if c.name == "delete_step"]
    assert deletes == []
