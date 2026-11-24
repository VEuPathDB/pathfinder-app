from __future__ import annotations

import pytest
from veupathdb.domain.strategy import (
    StepFilter,
    StepReport,
    StrategyStepNode,
    flatten_tree,
)

from strategist.services.strategies.commit_tree import CommitTarget, commit_tree
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
)


async def test_a_commit_writes_the_filter_and_runs_no_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    step = StrategyStepNode(
        id="A",
        search_name="GenesByMolecularWeight",
        filters=[StepFilter(name="matched_transcript_filter_array", value={})],
        reports=[
            StepReport(report_name="standard"),
            StepReport(report_name="fullRecord"),
        ],
    )

    await commit_tree(
        site_id="plasmodb",
        steps=flatten_tree(step),
        root_id="A",
        old=None,
        sync_state=WDKSyncState(),
        target=CommitTarget(name="test", description=""),
    )

    assert [(w.method, w.path.rsplit("/", 1)[-1]) for w in env.wdk.writes] == [
        ("POST", "steps"),
        ("PUT", "search-config"),
        ("POST", "strategies"),
    ]
