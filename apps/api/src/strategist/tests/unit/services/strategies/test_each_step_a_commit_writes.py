from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)

from strategist.services.strategies import commit_tree
from strategist.services.strategies.commit_tree import CommitTarget, CommittedTree
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.wdk_write_stubs import (
    accepts_every_value,
    skip_the_tree_put,
)

from ._counting_strategy_api import CountingStrategyAPI


@pytest.fixture
def counting_api(monkeypatch: pytest.MonkeyPatch) -> CountingStrategyAPI:
    api = CountingStrategyAPI()
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(commit_tree, "validate_parameters", accepts_every_value)
    skip_the_tree_put(monkeypatch)
    list_every_search_under(monkeypatch, "transcript")
    return api


def _leaf(step_id: str, search: str = "GenesByTaxon") -> StrategyStepNode:
    return StrategyStepNode(
        search_name=search,
        parameters={"organism": MultiPickValue(values=["Pf3D7"])},
        id=step_id,
    )


async def _commit(
    api: CountingStrategyAPI,
    root: StrategyStepNode,
    sync_state: WDKSyncState,
    before: StrategyStepNode | None = None,
) -> CommittedTree:
    if before is not None:
        api.holds(flatten_tree(before), sync_state)
    return await commit_tree.commit_tree(
        site_id="plasmodb",
        steps=flatten_tree(root),
        root_id=root.id,
        old=None
        if before is None
        else StrategyAst(record_type="transcript", root=before),
        sync_state=sync_state,
        target=CommitTarget(name="test", description=""),
    )


def _failed(committed: CommittedTree) -> list[str]:
    return [failure.step_id for failure in committed.failures]


def _deleted(api: CountingStrategyAPI) -> list[int]:
    return [
        i
        for call in api.named("delete_orphaned_steps")
        for i in call.kwargs["step_ids"]
    ]


async def test_a_step_that_lands_is_pushed(counting_api: CountingStrategyAPI) -> None:
    sync_state = WDKSyncState()

    committed = await _commit(counting_api, _leaf("A", "SearchA"), sync_state)

    assert (committed.pushed, _failed(committed)) == (["A"], [])
    assert sync_state.wdk_step_ids == {"A": 1001}


async def test_a_refused_step_skips_the_combine_above_it_and_not_its_sibling(
    counting_api: CountingStrategyAPI,
) -> None:
    counting_api.fail_on_search_names = {"SearchB"}
    sync_state = WDKSyncState()
    root = StrategyStepNode(
        id="J",
        search_name="__combine__",
        primary_input=_leaf("A", "SearchA"),
        secondary_input=_leaf("B", "SearchB"),
        operator=CombineOp.UNION,
    )

    committed = await _commit(counting_api, root, sync_state)

    assert (committed.pushed, _failed(committed), committed.skipped) == (
        ["A"],
        ["B"],
        ["J"],
    )
    assert committed.sync is None
    assert sync_state.wdk_step_ids == {"A": 1001}
    assert (
        sync_state.wdk_push_errors["B"]
        == "VEuPathDB service error: synthetic failure for SearchB"
    )


async def test_a_replaced_search_is_created_and_never_patched(
    counting_api: CountingStrategyAPI,
) -> None:
    """The node keeps its id and runs a new search, so WDK gets a new step."""
    sync_state = WDKSyncState(wdk_step_ids={"A": 440432473})

    committed = await _commit(
        counting_api,
        _leaf("A", "GenesByMicroarrayBirkholtz"),
        sync_state,
        before=_leaf("A", "GenesByRNASeqSu"),
    )

    assert _failed(committed) == []
    assert counting_api.named("update_step_search_config") == []
    created = counting_api.named("create_step")
    assert [call.kwargs["search_name"] for call in created] == [
        "GenesByMicroarrayBirkholtz"
    ]
    assert sync_state.wdk_step_ids["A"] != 440432473
    assert _deleted(counting_api) == [440432473]


async def test_a_recreate_that_fails_keeps_the_step_it_replaced(
    counting_api: CountingStrategyAPI,
) -> None:
    """The old step still runs under the strategy tree, so it stays."""
    counting_api.fail_on_search_names = {"GenesByMicroarrayBirkholtz"}
    sync_state = WDKSyncState(wdk_step_ids={"A": 440432473})

    committed = await _commit(
        counting_api,
        _leaf("A", "GenesByMicroarrayBirkholtz"),
        sync_state,
        before=_leaf("A", "GenesByRNASeqSu"),
    )

    assert _failed(committed) == ["A"]
    assert _deleted(counting_api) == []
    assert sync_state.wdk_step_ids == {"A": 440432473}


async def test_a_step_that_reaches_wdk_clears_its_earlier_refusal(
    counting_api: CountingStrategyAPI,
) -> None:
    """The refusal describes the last push, so a push that lands ends it."""
    sync_state = WDKSyncState(wdk_push_errors={"A": "422 organism: Invalid value"})

    committed = await _commit(counting_api, _leaf("A", "SearchA"), sync_state)

    assert committed.pushed == ["A"]
    assert sync_state.wdk_push_errors == {}


def _join(primary: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id="J",
        search_name="__combine__",
        primary_input=primary,
        secondary_input=_leaf("B", "GenesByTaxon"),
        operator=CombineOp.INTERSECT,
    )


async def test_a_combine_above_a_replaced_search_is_created_with_the_new_input(
    counting_api: CountingStrategyAPI,
) -> None:
    """The recreated parent takes the id of the step its child was recreated as."""
    sync_state = WDKSyncState(wdk_step_ids={"A": 440432473, "B": 200, "J": 300})

    committed = await _commit(
        counting_api,
        _join(_leaf("A", "GenesByMicroarrayBirkholtz")),
        sync_state,
        before=_join(_leaf("A", "GenesByRNASeqSu")),
    )

    assert _failed(committed) == []
    combines = counting_api.named("create_combined_step")
    assert [call.kwargs["primary_step_id"] for call in combines] == [
        sync_state.wdk_step_ids["A"]
    ]
    assert [call.kwargs["secondary_step_id"] for call in combines] == [200]
    assert sync_state.wdk_step_ids["J"] != 300


def _named(name: str, organism: str) -> StrategyStepNode:
    node = _leaf("A", "SearchA")
    node.display_name = name
    node.parameters = {"organism": MultiPickValue(values=[organism])}
    return node


async def test_a_patched_leaf_pushes_the_name_it_now_states(
    counting_api: CountingStrategyAPI,
) -> None:
    """WDK holds the name the step states, not the one it was created with."""
    await _commit(
        counting_api,
        _named("Genes with 1 to 2 predicted transmembrane domains", "TgME49"),
        WDKSyncState(wdk_step_ids={"A": 500}),
        before=_named("Genes with 1 to 7 predicted transmembrane domains", "Pf3D7"),
    )

    assert [
        call.kwargs["custom_name"]
        for call in counting_api.named("update_step_properties")
    ] == ["Genes with 1 to 2 predicted transmembrane domains"]


async def test_a_patched_leaf_whose_name_stood_still_writes_no_name(
    counting_api: CountingStrategyAPI,
) -> None:
    """A name WDK already holds costs no round trip of its own."""
    name = "Genes with 1 to 7 predicted transmembrane domains"

    await _commit(
        counting_api,
        _named(name, "TgME49"),
        WDKSyncState(wdk_step_ids={"A": 500}),
        before=_named(name, "Pf3D7"),
    )

    assert counting_api.named("update_step_properties") == []
    assert [
        call.kwargs["step_id"]
        for call in counting_api.named("update_step_search_config")
    ] == [500]
