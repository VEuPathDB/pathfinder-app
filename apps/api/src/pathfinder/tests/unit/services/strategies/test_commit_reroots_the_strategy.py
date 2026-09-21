from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    StepsMixin,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
)

from pathfinder.domain.strategy.operations import (
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepMetaOp,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import commit, live_counts, step_wdk_push, sync
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState

STRATEGY_ID = 330643473


@dataclass
class _Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


def _tree_ids(tree: WDKStepTree) -> list[int]:
    ids = [tree.step_id]
    for child in (tree.primary_input, tree.secondary_input):
        if child is not None:
            ids.extend(_tree_ids(child))
    return ids


@dataclass
class _RecordingAPI:
    """A WDK account that answers about the strategy tree it was last given."""

    calls: list[_Call] = field(default_factory=list)
    next_id: int = 440436300
    strategy_tree: WDKStepTree | None = None
    keeps_its_own_root: bool = False

    delete_orphaned_steps = StepsMixin.delete_orphaned_steps

    def named(self, name: str) -> list[_Call]:
        return [call for call in self.calls if call.name == name]

    def _alloc(self) -> int:
        self.next_id += 10
        return self.next_id

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del record_type, user_id
        step_id = self._alloc()
        self.calls.append(
            _Call("create_step", {"search_name": spec.search_name, "id": step_id})
        )
        return WDKIdentifier(id=step_id)

    async def create_combined_step(
        self, spec: CombinedStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del record_type, user_id
        step_id = self._alloc()
        self.calls.append(
            _Call(
                "create_combined_step",
                {
                    "primary_step_id": spec.primary_step_id,
                    "secondary_step_id": spec.secondary_step_id,
                    "operator": spec.boolean_operator.value,
                    "id": step_id,
                },
            )
        )
        return WDKIdentifier(id=step_id)

    async def update_step_search_config(self, **kwargs: Any) -> None:
        self.calls.append(
            _Call("update_step_search_config", {"step_id": kwargs.get("step_id")})
        )

    async def update_step_properties(self, **kwargs: Any) -> None:
        self.calls.append(_Call("update_step_properties", dict(kwargs)))

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self.calls.append(_Call("delete_step", {"step_id": step_id}))

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByTaxon",
            search_config=WDKSearchConfig(parameters={}),
        )

    async def create_strategy(self, step_tree: WDKStepTree, name: str, **_: Any) -> Any:
        del name
        self.calls.append(_Call("create_strategy", {"root": step_tree.step_id}))
        self.strategy_tree = step_tree
        return WDKIdentifier(id=STRATEGY_ID)

    async def update_strategy(
        self,
        strategy_id: int,
        step_tree: WDKStepTree | None = None,
        name: str | None = None,
        user_id: str | None = None,
    ) -> WDKStrategyDetails:
        del name, user_id
        self.calls.append(
            _Call(
                "update_strategy",
                {
                    "strategy_id": strategy_id,
                    "root": step_tree.step_id if step_tree else None,
                },
            )
        )
        if step_tree is not None and not self.keeps_its_own_root:
            self.strategy_tree = step_tree
        return await self.get_strategy(strategy_id)

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        tree = self.strategy_tree
        if tree is None:
            msg = "the fake holds no strategy"
            raise AssertionError(msg)
        return WDKStrategyDetails(
            strategy_id=strategy_id,
            name="Test",
            root_step_id=tree.step_id,
            step_tree=tree,
            steps={
                str(step_id): WDKStep(
                    id=step_id,
                    search_name="GenesByTaxon",
                    search_config=WDKSearchConfig(parameters={}),
                    estimated_size=132,
                )
                for step_id in _tree_ids(tree)
            },
        )


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> _RecordingAPI:
    recording = _RecordingAPI()
    for module in (commit, step_wdk_push, sync, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: recording)

    async def _noop_validate(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _noop_validate)

    async def _noop_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _noop_reconcile)

    async def _noop_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "persist_strategy_ast_to_conversation", _noop_persist)

    async def _listed_under(_search_name: str) -> str:
        return "transcript"

    async def _resolver(_site_id: str) -> Any:
        return _listed_under

    monkeypatch.setattr(sync, "make_record_type_resolver", _resolver)
    return recording


def _leaf(step_id: str, search: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search)


def _join(
    step_id: str, primary: StrategyStepNode, secondary: StrategyStepNode, op: CombineOp
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="__combine__",
        primary_input=primary,
        secondary_input=secondary,
        operator=op,
    )


def _seed(
    root: StrategyStepNode, wdk_step_ids: dict[str, int], api: _RecordingAPI
) -> StrategyMutationContext:
    session = StrategySession(site_id="toxodb")
    graph = StrategyGraph(graph_id="g1", name="Test", site_id="toxodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    tree = WDKStepTree(
        step_id=wdk_step_ids[root.id],
        primary_input=WDKStepTree(step_id=wdk_step_ids[root.primary_input_id or ""]),
        secondary_input=WDKStepTree(
            step_id=wdk_step_ids[root.secondary_input_id or ""]
        ),
    )
    api.strategy_tree = tree
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids),
        wdk_strategy_id=STRATEGY_ID,
        wdk_step_tree=tree,
    )
    return StrategyMutationContext(
        site_id="toxodb",
        strategy_session=session,
        conversation_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_a_replaced_search_re_roots_the_wdk_strategy(api: _RecordingAPI) -> None:
    """The recreated leaf and join are new WDK steps, so the strategy moves."""
    step_a = _leaf("step_a", "GenesByRNASeqSu")
    step_b = _leaf("step_b", "GenesByTaxon")
    root = _join("step_join", step_a, step_b, CombineOp.INTERSECT)
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 300}, api)

    result = await apply_and_commit(
        deps=deps,
        op=ReplaceSubtreeOp(
            step_id="step_a", subtree=_leaf("step_a", "GenesByMicroarrayBirkholtz")
        ),
    )

    sync_state = deps.strategy_session.sync_state
    assert sync_state is not None
    assert result.failures == []
    puts = api.named("update_strategy")
    assert [call.kwargs["root"] for call in puts] == [
        sync_state.wdk_step_ids["step_join"]
    ]
    assert sync_state.wdk_step_ids["step_join"] != 300


@pytest.mark.asyncio
async def test_the_steps_a_recreate_replaced_are_deleted_after_the_put(
    api: _RecordingAPI,
) -> None:
    """The put is what orphans them, so the delete follows it."""
    step_a = _leaf("step_a", "GenesByRNASeqSu")
    step_b = _leaf("step_b", "GenesByTaxon")
    root = _join("step_join", step_a, step_b, CombineOp.INTERSECT)
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 300}, api)

    result = await apply_and_commit(
        deps=deps,
        op=ReplaceSubtreeOp(
            step_id="step_a", subtree=_leaf("step_a", "GenesByMicroarrayBirkholtz")
        ),
    )

    sync_state = deps.strategy_session.sync_state
    assert sync_state is not None
    assert result.failures == []
    deleted = [call.kwargs["step_id"] for call in api.named("delete_step")]
    assert sorted(deleted) == [100, 300], "the replaced leaf and combine"
    assert sync_state.wdk_step_ids["step_a"] not in deleted
    assert sync_state.wdk_step_ids["step_join"] not in deleted
    names = [call.name for call in api.calls]
    assert names.index("update_strategy") < names.index("delete_step")


@pytest.mark.asyncio
async def test_a_recreate_whose_put_fails_deletes_nothing(
    api: _RecordingAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WDK still holds the old step in its tree, so deleting it is refused."""

    async def _refuse(**_kwargs: Any) -> SyncResult:
        message = "500: the site is down"
        raise WDKError(message)

    monkeypatch.setattr(commit, "sync_strategy_for_site", _refuse)
    step_a = _leaf("step_a", "GenesByRNASeqSu")
    step_b = _leaf("step_b", "GenesByTaxon")
    root = _join("step_join", step_a, step_b, CombineOp.INTERSECT)
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 300}, api)

    await apply_and_commit(
        deps=deps,
        op=ReplaceSubtreeOp(
            step_id="step_a", subtree=_leaf("step_a", "GenesByMicroarrayBirkholtz")
        ),
    )

    assert api.named("delete_step") == []


@pytest.mark.asyncio
async def test_a_re_rooted_union_re_roots_the_wdk_strategy(api: _RecordingAPI) -> None:
    """An operator change recreates the root, so WDK is told about the new one."""
    step_a = _leaf("step_a", "GenesByMolecularWeight")
    step_b = _leaf("step_b", "GenesByTaxon")
    root = _join("step_join", step_a, step_b, CombineOp.INTERSECT)
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 440436303}, api)

    result = await apply_and_commit(
        deps=deps,
        op=UpdateCombineOperatorOp(step_id="step_join", operator=CombineOp.UNION),
    )

    sync_state = deps.strategy_session.sync_state
    assert sync_state is not None
    new_root = sync_state.wdk_step_ids["step_join"]
    assert result.failures == []
    assert new_root != 440436303
    assert [call.kwargs["root"] for call in api.named("update_strategy")] == [new_root]
    assert api.strategy_tree is not None
    assert api.strategy_tree.step_id == new_root


@pytest.mark.asyncio
async def test_a_step_the_strategy_does_not_hold_is_a_failed_push(
    api: _RecordingAPI,
) -> None:
    """A detached step has no result, so the edit is not reported as a success."""
    api.keeps_its_own_root = True
    step_a = _leaf("step_a", "GenesByMolecularWeight")
    step_b = _leaf("step_b", "GenesByTaxon")
    root = _join("step_join", step_a, step_b, CombineOp.INTERSECT)
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 440436303}, api)

    result = await apply_and_commit(
        deps=deps,
        op=UpdateCombineOperatorOp(step_id="step_join", operator=CombineOp.UNION),
    )

    sync_state = deps.strategy_session.sync_state
    assert sync_state is not None
    assert [failure.step_id for failure in result.failures] == ["step_join"]
    assert "step_join" in sync_state.wdk_push_errors


@pytest.mark.asyncio
async def test_a_later_put_that_holds_the_step_ends_the_detached_record(
    api: _RecordingAPI,
) -> None:
    """The record names the last put, so a strategy that lists the step ends it."""
    api.keeps_its_own_root = True
    root = _join(
        "step_join",
        _leaf("step_a", "GenesByMolecularWeight"),
        _leaf("step_b", "GenesByTaxon"),
        CombineOp.INTERSECT,
    )
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 440436303}, api)
    await apply_and_commit(
        deps=deps,
        op=UpdateCombineOperatorOp(step_id="step_join", operator=CombineOp.UNION),
    )
    sync_state = deps.strategy_session.sync_state
    assert sync_state is not None
    assert "step_join" in sync_state.wdk_push_errors

    api.keeps_its_own_root = False
    result = await apply_and_commit(
        deps=deps, op=UpdateStepMetaOp(step_id="step_a", display_name="renamed")
    )

    assert result.failures == []
    assert sync_state.wdk_push_errors == {}
