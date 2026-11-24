from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree

from strategist.services.strategies.commit_tree import (
    CommitTarget,
    CommittedTree,
    commit_tree,
)
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
)

_SORTED = [{"name": "wdk_weight", "direction": "DESC"}]


def _union(weight: int | None) -> StrategyStepNode:
    return StrategyStepNode(
        id="union",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(
            id="a", search_name="GenesByTaxon", wdk_weight=weight
        ),
        secondary_input=StrategyStepNode(
            id="b", search_name="GenesByTaxon", wdk_weight=weight
        ),
    )


async def _commit(weight: int | None, sync_state: WDKSyncState) -> CommittedTree:
    return await commit_tree(
        site_id="plasmodb",
        steps=flatten_tree(_union(weight)),
        root_id="union",
        old=None,
        sync_state=sync_state,
        target=CommitTarget(name="test", description=""),
    )


async def test_a_new_leaf_carries_its_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch)

    await _commit(1, WDKSyncState())

    assert [
        w.body["searchConfig"].get("wdkWeight")
        for w in env.wdk.written("POST", "/steps")
        if w.body["searchName"] == "GenesByTaxon"
    ] == [1, 1]


async def test_a_ranked_result_opens_sorted_by_weight_highest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    sync_state = WDKSyncState()

    await _commit(1, sync_state)

    root = env.wdk.steps[sync_state.wdk_step_ids["union"]]
    assert root["displayPreferences"] == {"sortColumns": _SORTED}


async def test_an_unweighted_result_keeps_the_sites_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)

    await _commit(None, WDKSyncState())

    assert env.wdk.written("PATCH") == []


async def test_a_sort_the_site_refuses_is_the_roots_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    env.wdk.refuses_patches = True

    committed = await _commit(1, WDKSyncState())

    assert (sorted(committed.pushed), [f.step_id for f in committed.failures]) == (
        ["a", "b", "union"],
        ["union"],
    )
    assert committed.failures[0].error.startswith(
        "PlasmoDB (Plasmodium) did not sort the ranked result by score, so it is not "
        "ranked: HTTP 422"
    )
    assert committed.sync is not None
