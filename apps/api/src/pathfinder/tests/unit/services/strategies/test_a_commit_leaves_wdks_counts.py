"""Every count a commit leaves behind is the one VEuPathDB answers.

A push changes what one step returns, and every combine above it with it. The
commit reads the whole strategy back before it emits or persists anything, so
the session, the graph snapshot and the stored strategy all carry one set of
numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.wdk import (
    NewStepSpec,
    PatchStepSpec,
    StepsMixin,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
    WDKStrategyDetails,
)
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.tools.standalone.stream_parts import build_graph_snapshot_payload
from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import (
    commit,
    live_counts,
    stated_sides,
    step_wdk_push,
    sync,
)
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync import (
    SyncResult,
    build_step_tree_from_graph,
)
from pathfinder.services.strategies.sync_state import WDKSyncState

_SITE = "vectorbase"
_STRATEGY = 900

_TEXT = "step_text"
_GO = "step_go"
_INNER = "step_inner"
_IPR = "step_ipr"
_OUTER = "step_outer"

_WDK_IDS = {_TEXT: 11, _GO: 12, _INNER: 13, _IPR: 14, _OUTER: 15}

# What the session recorded before the edit: the text leaf never counted, and
# both combines carry the number the tree returned before it was rebound.
_RECORDED = {_TEXT: 0, _GO: 152, _INNER: 152, _IPR: 70, _OUTER: 152}

# What the site answers for the tree the edit leaves behind.
_LIVE = {_TEXT: 71, _GO: 152, _INNER: 159, _IPR: 70, _OUTER: 159}


@dataclass
class _StubAPI:
    """The WDK calls a parameter edit makes, with the counts it reads back."""

    live: dict[str, int | None]
    next_id: int = 9000

    delete_orphaned_steps = StepsMixin.delete_orphaned_steps

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del step_id, user_id

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del spec, record_type, user_id
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def create_combined_step(self, **_kwargs: Any) -> WDKIdentifier:
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def update_step_search_config(self, **_kwargs: Any) -> None:
        return None

    async def update_step_properties(
        self, step_id: int, spec: PatchStepSpec, *, user_id: str | None = None
    ) -> None:
        del step_id, spec, user_id

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByText",
            search_config=WDKSearchConfig(parameters={}),
        )

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "name": "edited",
                "rootStepId": _WDK_IDS[_OUTER],
                "stepTree": {"stepId": _WDK_IDS[_OUTER]},
                "steps": {
                    str(_WDK_IDS[local_id]): {
                        "id": _WDK_IDS[local_id],
                        "searchName": "GenesByText",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": size,
                    }
                    for local_id, size in self.live.items()
                },
            }
        )


_SITE_IS_DOWN = OSError("the site is not answering")


def _leaf(step_id: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name="GenesByText")


def _combine(
    step_id: str, primary: StrategyStepNode, secondary: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="__combine__",
        primary_input=primary,
        secondary_input=secondary,
        operator=CombineOp.UNION,
    )


def _root() -> StrategyStepNode:
    return _combine(_OUTER, _combine(_INNER, _leaf(_TEXT), _leaf(_GO)), _leaf(_IPR))


def _seeded_session() -> StrategyMutationContext:
    """A pushed strategy whose recorded counts describe the tree before the edit."""
    session = StrategySession(site_id=_SITE)
    graph = StrategyGraph(graph_id="g1", name="proteases", site_id=_SITE)
    graph.record_type = "transcript"
    root = _root()
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    sync_state = WDKSyncState(
        wdk_step_ids=dict(_WDK_IDS),
        step_counts=dict(_RECORDED),
        wdk_strategy_id=_STRATEGY,
    )
    # The edit rebinds a leaf and leaves the shape alone, so the commit puts no
    # new step tree and the counts have only the live read to come from.
    sync_state.wdk_step_tree = build_step_tree_from_graph(root, dict(_WDK_IDS))
    session.sync_state = sync_state
    return StrategyMutationContext(
        site_id=_SITE,
        strategy_session=session,
        conversation_id=uuid4(),
    )


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> _StubAPI:
    api = _StubAPI(live=dict(_LIVE))
    for module in (commit, step_wdk_push, sync, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)

    async def _noop_validate(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _noop_validate)

    async def _echo_parameters(*_args: Any, **kwargs: Any) -> ValidatedParams:
        params: dict[str, ParamValue] = dict(kwargs.get("parameters") or {})
        return ValidatedParams(params=params, record_class="transcript")

    monkeypatch.setattr(stated_sides, "validate_parameters", _echo_parameters)

    async def _noop_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _noop_reconcile)

    async def _refuse_sync(**_kwargs: Any) -> SyncResult:
        msg = "a parameter edit leaves the step tree alone and puts nothing"
        raise AssertionError(msg)

    monkeypatch.setattr(commit, "sync_strategy_for_site", _refuse_sync)

    async def _noop_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "persist_strategy_ast_to_conversation", _noop_persist)
    return api


def _rebind_text() -> UpdateStepParamsOp:
    return UpdateStepParamsOp(
        step_id=_TEXT,
        parameters={"organism": MultiPickValue(values=["AgamP4"])},
    )


class TestTheSessionHoldsTheLiveCounts:
    @pytest.mark.asyncio
    async def test_every_step_carries_the_number_the_site_answers(
        self, wdk: _StubAPI
    ) -> None:
        deps = _seeded_session()

        await apply_and_commit(deps=deps, op=_rebind_text())

        sync_state = deps.strategy_session.sync_state
        assert sync_state is not None
        assert sync_state.step_counts == _LIVE

    @pytest.mark.asyncio
    async def test_a_step_the_site_leaves_out_is_unknown(self, wdk: _StubAPI) -> None:
        """A local step the strategy does not hold answers no count at all."""
        wdk.live.pop(_IPR)
        deps = _seeded_session()

        await apply_and_commit(deps=deps, op=_rebind_text())

        sync_state = deps.strategy_session.sync_state
        assert sync_state is not None
        assert sync_state.step_counts == {**_LIVE, _IPR: None}


class TestTheSnapshotCarriesTheSameNumbers:
    @pytest.mark.asyncio
    async def test_the_snapshot_holds_no_null_and_no_stale_root(
        self, wdk: _StubAPI
    ) -> None:
        deps = _seeded_session()

        await apply_and_commit(deps=deps, op=_rebind_text())

        session = deps.strategy_session
        graph = session.get_graph(None)
        assert graph is not None
        payload = build_graph_snapshot_payload(session, graph)
        assert {node.id: node.estimated_size for node in payload.nodes} == _LIVE

    @pytest.mark.asyncio
    async def test_the_snapshot_root_count_is_the_live_root(
        self, wdk: _StubAPI
    ) -> None:
        deps = _seeded_session()

        await apply_and_commit(deps=deps, op=_rebind_text())

        session = deps.strategy_session
        graph = session.get_graph(None)
        assert graph is not None
        assert build_graph_snapshot_payload(session, graph).gene_count == _LIVE[_OUTER]


class TestAFailedReadLeavesNoNumberOnTheEditedBranch:
    @pytest.fixture
    def unreadable(self, wdk: _StubAPI, monkeypatch: pytest.MonkeyPatch) -> _StubAPI:
        async def _down(*_args: Any, **_kwargs: Any) -> WDKStrategyDetails:
            raise _SITE_IS_DOWN

        monkeypatch.setattr(wdk, "get_strategy", _down)
        return wdk

    @pytest.mark.asyncio
    async def test_the_leaf_and_every_combine_above_it_are_unknown(
        self, unreadable: _StubAPI
    ) -> None:
        """The branch the edit changed reads as unknown; the rest stands."""
        deps = _seeded_session()

        await apply_and_commit(deps=deps, op=_rebind_text())

        sync_state = deps.strategy_session.sync_state
        assert sync_state is not None
        assert sync_state.step_counts == {
            **_RECORDED,
            _TEXT: None,
            _INNER: None,
            _OUTER: None,
        }
