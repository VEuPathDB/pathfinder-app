from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
    walk,
)

from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import step_wdk_push
from strategist.services.strategies.step_push_planner import plan_step_pushes
from strategist.services.strategies.step_wdk_push import (
    PushOutcome,
    push_steps_with_plan,
)
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under

from ._counting_strategy_api import CountingStrategyAPI


async def _noop_validate_plan_params(*_args: object, **_kwargs: object) -> set[str]:
    return set()


@pytest.fixture
def counting_api(monkeypatch: pytest.MonkeyPatch) -> CountingStrategyAPI:
    api = CountingStrategyAPI()
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(
        step_wdk_push, "_validate_plan_params", _noop_validate_plan_params
    )
    list_every_search_under(monkeypatch, "transcript")
    return api


def _leaf(step_id: str, search: str = "GenesByTaxon") -> StrategyStepNode:
    return StrategyStepNode(
        search_name=search,
        parameters={"organism": MultiPickValue(values=["Pf3D7"])},
        id=step_id,
    )


def _populate_graph(graph: StrategyGraph, ast: StrategyAst) -> None:
    for step in walk(ast.root):
        graph.steps.update(flatten_tree(step))
    graph.record_type = ast.record_type
    graph.recompute_roots()


def _rejected(step_id: str) -> StepPushFailure:
    return StepPushFailure(
        step_id=step_id, search_name="SearchB", error="refused", wdk_status=422
    )


def test_push_outcome_partial_property_true_only_when_failed_nonempty() -> None:
    assert PushOutcome(succeeded=["a"], failures=[]).partial is False
    assert PushOutcome(succeeded=[], failures=[]).partial is False
    assert PushOutcome(succeeded=["a"], failures=[_rejected("b")]).partial is True
    assert PushOutcome(succeeded=[], failures=[_rejected("b")]).partial is True


async def test_push_outcome_all_succeeded(counting_api: CountingStrategyAPI) -> None:
    a = _leaf("A", "SearchA")
    ast = StrategyAst(record_type="transcript", root=a)

    graph = StrategyGraph("g1", "test", "plasmodb")
    sync_state = WDKSyncState()
    _populate_graph(graph, ast)

    plan = plan_step_pushes(old_ast=None, new_ast=ast, existing_wdk_ids={})
    outcome = await push_steps_with_plan(graph, sync_state, "plasmodb", plan)

    assert outcome.succeeded == ["A"]
    assert outcome.failed == []
    assert outcome.partial is False
    assert sync_state.wdk_step_ids == {"A": 1001}


async def test_push_outcome_partial_failure_continues_after_failed_step(
    counting_api: CountingStrategyAPI,
) -> None:
    counting_api.fail_on_search_names = {"SearchB"}

    a = _leaf("A", "SearchA")
    b = _leaf("B", "SearchB")
    c = _leaf("C", "SearchC")
    graph_a = StrategyGraph("g1", "test", "plasmodb")
    graph_a.steps = flatten_tree(a)
    graph_a.record_type = "transcript"
    graph_a.recompute_roots()

    sync_state = WDKSyncState()
    plan_a = plan_step_pushes(
        old_ast=None,
        new_ast=StrategyAst(record_type="transcript", root=a),
        existing_wdk_ids={},
    )
    await push_steps_with_plan(graph_a, sync_state, "plasmodb", plan_a)
    a_wdk_id = sync_state.wdk_step_ids["A"]

    graph_b = StrategyGraph("g1", "test", "plasmodb")
    graph_b.steps = flatten_tree(b)
    graph_b.record_type = "transcript"
    graph_b.recompute_roots()
    plan_b = plan_step_pushes(
        old_ast=None,
        new_ast=StrategyAst(record_type="transcript", root=b),
        existing_wdk_ids={},
    )
    outcome_b = await push_steps_with_plan(graph_b, sync_state, "plasmodb", plan_b)

    graph_c = StrategyGraph("g1", "test", "plasmodb")
    graph_c.steps = flatten_tree(c)
    graph_c.record_type = "transcript"
    graph_c.recompute_roots()
    plan_c = plan_step_pushes(
        old_ast=None,
        new_ast=StrategyAst(record_type="transcript", root=c),
        existing_wdk_ids={},
    )
    outcome_c = await push_steps_with_plan(graph_c, sync_state, "plasmodb", plan_c)

    assert outcome_b.succeeded == []
    assert outcome_b.failed == ["B"]
    assert outcome_b.partial is True

    assert outcome_c.succeeded == ["C"]
    assert outcome_c.failed == []
    assert sync_state.wdk_step_ids == {"A": a_wdk_id, "C": 1002}
    assert (
        sync_state.wdk_push_errors["B"]
        == "VEuPathDB service error: synthetic failure for SearchB"
    )


async def test_push_outcome_all_failed(counting_api: CountingStrategyAPI) -> None:
    counting_api.fail_on_search_names = {"SearchA", "SearchB", "SearchC"}

    a = _leaf("A", "SearchA")
    b = _leaf("B", "SearchB")
    c = _leaf("C", "SearchC")

    sync_state = WDKSyncState()

    for step_id, node in [("A", a), ("B", b), ("C", c)]:
        graph = StrategyGraph("g1", "test", "plasmodb")
        graph.steps = flatten_tree(node)
        graph.record_type = "transcript"
        graph.recompute_roots()
        plan = plan_step_pushes(
            old_ast=None,
            new_ast=StrategyAst(record_type="transcript", root=node),
            existing_wdk_ids={},
        )
        outcome = await push_steps_with_plan(graph, sync_state, "plasmodb", plan)
        assert outcome.succeeded == []
        assert outcome.failed == [step_id]
        assert outcome.partial is True

    assert sync_state.wdk_step_ids == {}
    assert set(sync_state.wdk_push_errors.keys()) == {"A", "B", "C"}


async def test_a_replaced_search_is_created_and_never_patched(
    counting_api: CountingStrategyAPI,
) -> None:
    """The node keeps its id and runs a new search, so WDK gets a new step."""
    old = _leaf("A", "GenesByRNASeqSu")
    new = _leaf("A", "GenesByMicroarrayBirkholtz")
    graph = StrategyGraph("g1", "test", "plasmodb")
    _populate_graph(graph, StrategyAst(record_type="transcript", root=new))
    sync_state = WDKSyncState(wdk_step_ids={"A": 440432473})

    plan = plan_step_pushes(
        old_ast=StrategyAst(record_type="transcript", root=old),
        new_ast=StrategyAst(record_type="transcript", root=new),
        existing_wdk_ids=sync_state.wdk_step_ids,
    )
    outcome = await push_steps_with_plan(graph, sync_state, "plasmodb", plan)

    assert outcome.failed == []
    assert counting_api.named("update_step_search_config") == []
    created = counting_api.named("create_step")
    assert [call.kwargs["search_name"] for call in created] == [
        "GenesByMicroarrayBirkholtz"
    ]
    assert sync_state.wdk_step_ids["A"] != 440432473
    assert outcome.recreated_wdk_ids == {"A": 440432473}, "the replaced id is carried"


async def test_a_recreate_that_fails_reports_no_replaced_id(
    counting_api: CountingStrategyAPI,
) -> None:
    """The old step still runs under the strategy tree, so it stays."""
    counting_api.fail_on_search_names = {"GenesByMicroarrayBirkholtz"}
    old = _leaf("A", "GenesByRNASeqSu")
    new = _leaf("A", "GenesByMicroarrayBirkholtz")
    graph = StrategyGraph("g1", "test", "plasmodb")
    _populate_graph(graph, StrategyAst(record_type="transcript", root=new))
    sync_state = WDKSyncState(wdk_step_ids={"A": 440432473})

    outcome = await push_steps_with_plan(
        graph,
        sync_state,
        "plasmodb",
        plan_step_pushes(
            old_ast=StrategyAst(record_type="transcript", root=old),
            new_ast=StrategyAst(record_type="transcript", root=new),
            existing_wdk_ids=sync_state.wdk_step_ids,
        ),
    )

    assert outcome.failed == ["A"]
    assert outcome.recreated_wdk_ids == {}
    assert sync_state.wdk_step_ids == {"A": 440432473}, "the id it had is kept"


async def test_a_step_that_reaches_wdk_clears_its_earlier_refusal(
    counting_api: CountingStrategyAPI,
) -> None:
    """The refusal describes the last push, so a push that lands ends it."""
    node = _leaf("A", "SearchA")
    graph = StrategyGraph("g1", "test", "plasmodb")
    _populate_graph(graph, StrategyAst(record_type="transcript", root=node))
    sync_state = WDKSyncState(wdk_push_errors={"A": "422 organism: Invalid value"})

    plan = plan_step_pushes(
        old_ast=None,
        new_ast=StrategyAst(record_type="transcript", root=node),
        existing_wdk_ids={},
    )
    outcome = await push_steps_with_plan(graph, sync_state, "plasmodb", plan)

    assert outcome.succeeded == ["A"]
    assert sync_state.wdk_push_errors == {}


async def test_a_combine_above_a_replaced_search_is_created_with_the_new_input(
    counting_api: CountingStrategyAPI,
) -> None:
    """The recreated parent takes the id of the step its child was recreated as."""
    old_leaf = _leaf("A", "GenesByRNASeqSu")
    new_leaf = _leaf("A", "GenesByMicroarrayBirkholtz")
    other = _leaf("B", "GenesByTaxon")
    old_root = StrategyStepNode(
        id="J",
        search_name="__combine__",
        primary_input=old_leaf,
        secondary_input=other,
        operator=CombineOp.INTERSECT,
    )
    new_root = StrategyStepNode(
        id="J",
        search_name="__combine__",
        primary_input=new_leaf,
        secondary_input=other,
        operator=CombineOp.INTERSECT,
    )
    graph = StrategyGraph("g1", "test", "plasmodb")
    _populate_graph(graph, StrategyAst(record_type="transcript", root=new_root))
    sync_state = WDKSyncState(wdk_step_ids={"A": 440432473, "B": 200, "J": 300})

    outcome = await push_steps_with_plan(
        graph,
        sync_state,
        "plasmodb",
        plan_step_pushes(
            old_ast=StrategyAst(record_type="transcript", root=old_root),
            new_ast=StrategyAst(record_type="transcript", root=new_root),
            existing_wdk_ids=sync_state.wdk_step_ids,
        ),
    )

    assert outcome.failed == []
    combines = counting_api.named("create_combined_step")
    assert [call.kwargs["primary_step_id"] for call in combines] == [
        sync_state.wdk_step_ids["A"]
    ]
    assert [call.kwargs["secondary_step_id"] for call in combines] == [200]
    assert sync_state.wdk_step_ids["J"] != 300


async def test_a_patched_leaf_pushes_the_name_it_now_states(
    counting_api: CountingStrategyAPI,
) -> None:
    """WDK holds the name the step states, not the one it was created with."""
    before = _leaf("A", "SearchA")
    before.display_name = "Genes with 1 to 7 predicted transmembrane domains"
    after = _leaf("A", "SearchA")
    after.display_name = "Genes with 1 to 2 predicted transmembrane domains"
    after.parameters = {"organism": MultiPickValue(values=["TgME49"])}
    new_ast = StrategyAst(record_type="transcript", root=after)

    graph = StrategyGraph("g1", "test", "plasmodb")
    _populate_graph(graph, new_ast)
    sync_state = WDKSyncState(wdk_step_ids={"A": 500})
    plan = plan_step_pushes(
        old_ast=StrategyAst(record_type="transcript", root=before),
        new_ast=new_ast,
        existing_wdk_ids={"A": 500},
    )

    await push_steps_with_plan(graph, sync_state, "plasmodb", plan)

    assert [
        call.kwargs["custom_name"]
        for call in counting_api.named("update_step_properties")
    ] == ["Genes with 1 to 2 predicted transmembrane domains"]


async def test_a_patched_leaf_whose_name_stood_still_writes_no_name(
    counting_api: CountingStrategyAPI,
) -> None:
    """A name WDK already holds costs no round trip of its own."""
    before = _leaf("A", "SearchA")
    before.display_name = "Genes with 1 to 7 predicted transmembrane domains"
    after = _leaf("A", "SearchA")
    after.display_name = before.display_name
    after.parameters = {"organism": MultiPickValue(values=["TgME49"])}
    new_ast = StrategyAst(record_type="transcript", root=after)

    graph = StrategyGraph("g1", "test", "plasmodb")
    _populate_graph(graph, new_ast)
    sync_state = WDKSyncState(wdk_step_ids={"A": 500})
    plan = plan_step_pushes(
        old_ast=StrategyAst(record_type="transcript", root=before),
        new_ast=new_ast,
        existing_wdk_ids={"A": 500},
    )

    await push_steps_with_plan(graph, sync_state, "plasmodb", plan)

    assert counting_api.named("update_step_properties") == []
    assert counting_api.named("update_step_search_config") != []
