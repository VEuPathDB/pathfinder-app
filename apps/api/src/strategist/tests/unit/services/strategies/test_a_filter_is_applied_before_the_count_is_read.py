from __future__ import annotations

import pytest
from veupathdb.domain.strategy import StepFilter, StrategyStepNode, flatten_tree

from strategist.services.strategies.commit_tree import (
    CommitTarget,
    CommittedTree,
    commit_tree,
)
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
)

_STEP = "step_text"


async def _commit(sync_state: WDKSyncState) -> CommittedTree:
    step = StrategyStepNode(
        id=_STEP,
        search_name="GenesByText",
        filters=[
            StepFilter(name="matched_transcript_filter_array", value={"values": ["N"]})
        ],
    )
    return await commit_tree(
        site_id="plasmodb",
        steps=flatten_tree(step),
        root_id=_STEP,
        old=None,
        sync_state=sync_state,
        target=CommitTarget(name="test", description=""),
    )


async def test_the_filter_reaches_the_step_before_the_strategy_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)

    await _commit(WDKSyncState())

    assert [(w.method, w.path.rsplit("/", 1)[-1]) for w in env.wdk.writes] == [
        ("POST", "steps"),
        ("PUT", "search-config"),
        ("POST", "strategies"),
    ]


async def test_the_result_reports_the_count_and_links_to_its_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)
    sync_state = WDKSyncState()

    committed = await _commit(sync_state)

    assert committed.sync is not None
    assert (committed.sync.counts, committed.sync.root_count) == ({_STEP: 100}, 100)
    assert sync_state.step_counts == {_STEP: 100}
    assert committed.sync.wdk_url == (
        "https://qa.plasmodb.org/plasmo.qa/app/workspace/strategies/"
        f"{sync_state.wdk_strategy_id}/{sync_state.wdk_step_ids[_STEP]}"
        "/summary:_default"
    )
