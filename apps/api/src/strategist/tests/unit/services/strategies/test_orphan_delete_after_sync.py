"""A step is orphaned by the strategy put, so it is deleted after it.

WDK refuses to delete a step the stored strategy still references. Deleting
before the push guarantees the refusal, and dropping the local id anyway means
nothing knows the step exists to retry it.
"""

from __future__ import annotations

from typing import Any, override
from uuid import uuid4

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError

from strategist.domain.strategy.operations import DeleteResolution, DeleteStepOp
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies import commit, commit_tree
from strategist.services.strategies._tree_write import WrittenTree
from strategist.services.strategies.commit import apply_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.recording_wdk import (
    RecordingWDK,
    held_by_the_site,
    served,
)
from strategist.tests._support.wdk_write_stubs import serve_the_site

_STILL_REFERENCED = "409: step belongs to a strategy"


class _Recorder(RecordingWDK):
    def __init__(self) -> None:
        super().__init__()
        self.order: list[str] = []
        self.refused: set[int] = set()

    @override
    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        self.order.append(f"delete:{step_id}")
        if step_id in self.refused:
            raise WDKError(_STILL_REFERENCED, status=409)
        await super().delete_step(step_id, user_id=user_id)


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    api = _Recorder()
    monkeypatch.setitem(served, "site", api)
    serve_the_site(monkeypatch, api)

    async def _put(*_args: Any) -> WrittenTree:
        api.order.append("sync")
        return WrittenTree(strategy_id=42, root_step_id=0, created=False)

    async def _no_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit_tree, "put_the_tree", _put)
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
    held_by_the_site(session)
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
        wdk.refused = {100}
        deps = _deps({"A": 100, "B": 200, "C": 300})

        await _drop_a(deps)

        sync = deps.strategy_session.sync_state
        assert sync is not None
        assert sync.wdk_step_ids.get("A") == 100

    @pytest.mark.asyncio
    async def test_a_deleted_id_is_forgotten(self, wdk: _Recorder) -> None:
        wdk.refused = {100}
        deps = _deps({"A": 100, "B": 200, "C": 300})

        await _drop_a(deps)

        sync = deps.strategy_session.sync_state
        assert sync is not None
        assert "C" not in sync.wdk_step_ids

    @pytest.mark.asyncio
    async def test_every_id_is_forgotten_when_wdk_accepts(self, wdk: _Recorder) -> None:
        deps = _deps({"A": 100, "B": 200, "C": 300})

        await _drop_a(deps)

        sync = deps.strategy_session.sync_state
        assert sync is not None
        remaining = sync.wdk_step_ids
        assert "A" not in remaining
        assert "C" not in remaining
