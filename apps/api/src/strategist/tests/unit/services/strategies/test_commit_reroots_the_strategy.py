from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyStepNode,
    flatten_tree,
    wdk_search_name,
)
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    WDKStepTree,
)

from strategist.domain.strategy.operations import (
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepMetaOp,
)
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies import commit, commit_tree, record_classes
from strategist.services.strategies.commit import apply_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.record_classes import unclassed_step_failure
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from strategist.tests._support.recording_wdk import Call, RecordingWDK
from strategist.tests._support.wdk_write_stubs import serve_the_site

STRATEGY_ID = 330643473


class _RecordingAPI(RecordingWDK):
    def __init__(self) -> None:
        super().__init__(next_id=440436300)

    @property
    def keeps_its_own_root(self) -> bool:
        return self.wdk.keeps_its_own_tree

    @keeps_its_own_root.setter
    def keeps_its_own_root(self, keeps: bool) -> None:
        self.wdk.keeps_its_own_tree = keeps

    @property
    def strategy_tree(self) -> WDKStepTree:
        return WDKStepTree.model_validate(self.wdk.strategies[STRATEGY_ID]["stepTree"])


def _roots(calls: list[Call]) -> list[int]:
    return [call.kwargs["step_tree"].step_id for call in calls]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> _RecordingAPI:
    recording = _RecordingAPI()
    serve_the_site(monkeypatch, recording)

    async def _noop_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "persist_strategy_ast_to_conversation", _noop_persist)

    async def _listed_under(_search_name: str) -> str:
        return "transcript"

    async def _resolver(_site_id: str) -> Any:
        return _listed_under

    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
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
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids), wdk_strategy_id=STRATEGY_ID
    )
    api.holds(graph.steps, session.sync_state, root_id=root.id, name="Test")
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
    assert _roots(puts) == [sync_state.wdk_step_ids["step_join"]]
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

    async def _refuse(*_args: Any) -> None:
        message = "500: the site is down"
        raise WDKError(message)

    monkeypatch.setattr(commit_tree, "put_the_tree", _refuse)
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
    assert _roots(api.named("update_strategy")) == [new_root]
    assert api.strategy_tree is not None
    assert api.strategy_tree.step_id == new_root


@pytest.mark.asyncio
async def test_a_tree_the_strategy_does_not_hold_after_the_put_is_a_failed_push(
    api: _RecordingAPI,
) -> None:
    """The edit is not reported as a success, and the old tree stays recorded."""
    api.keeps_its_own_root = True
    step_a = _leaf("step_a", "GenesByMolecularWeight")
    step_b = _leaf("step_b", "GenesByTaxon")
    root = _join("step_join", step_a, step_b, CombineOp.INTERSECT)
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 440436303}, api)
    held_before = api.strategy_tree

    result = await apply_and_commit(
        deps=deps,
        op=UpdateCombineOperatorOp(step_id="step_join", operator=CombineOp.UNION),
    )

    assert [failure.step_id for failure in result.failures] == ["step_join"]
    assert "not the tree written" in result.failures[0].error
    assert ensure_sync_state(deps.strategy_session).wdk_step_tree == held_before


@pytest.mark.asyncio
async def test_the_next_put_the_strategy_holds_records_the_tree(
    api: _RecordingAPI,
) -> None:
    """A tree the strategy did not hold is put again by the next edit."""
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

    api.keeps_its_own_root = False
    result = await apply_and_commit(
        deps=deps, op=UpdateStepMetaOp(step_id="step_a", display_name="renamed")
    )

    assert result.failures == []
    assert len(api.named("update_strategy")) == 2
    assert ensure_sync_state(deps.strategy_session).wdk_step_tree == api.strategy_tree


@pytest.mark.asyncio
async def test_a_root_the_site_lists_no_class_for_is_a_failed_push(
    api: _RecordingAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _unlisted(_search_name: str) -> None:
        return None

    async def _resolver(_site_id: str) -> Any:
        return _unlisted

    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
    root = _join(
        "step_join",
        _leaf("step_a", "GenesByMolecularWeight"),
        _leaf("step_b", "GenesByTaxon"),
        CombineOp.INTERSECT,
    )
    deps = _seed(root, {"step_a": 100, "step_b": 200, "step_join": 440436303}, api)

    result = await apply_and_commit(
        deps=deps,
        op=UpdateCombineOperatorOp(step_id="step_join", operator=CombineOp.UNION),
    )

    graph = deps.strategy_session.graph
    assert graph is not None
    unclassed = unclassed_step_failure(
        "step_join", wdk_search_name(graph.steps["step_join"])
    )
    assert (result.failures, result.sync_result) == ([unclassed], None)
