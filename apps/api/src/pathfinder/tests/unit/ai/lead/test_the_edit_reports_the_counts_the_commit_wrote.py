"""The numbers the Lead reports after an edit are the session's own.

The commit reads the whole strategy back from VEuPathDB before it returns, so
the edit reports what the graph snapshot and the stored strategy carry. A
second read of its own would answer a different moment.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    renumber_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SEARCH = "GenesByRNASeqEvidence"
_CRITERION = "gametocyte_expression"
_WRITTEN_THROUGH = 71


def _carrier() -> Criterion:
    return Criterion(
        id=_CRITERION,
        text="upregulated in gametocytes",
        search_name=_SEARCH,
        resolved_params={
            "organism": MultiPickValue(values=["Pf3D7"]),
            "dataset": StringValue(value="all_rnaseq"),
        },
        defaulted_params=["dataset"],
    )


def _option() -> Criterion:
    return Criterion(
        id="sexual_stage_option",
        text="use the sexual stage dataset",
        search_name=_SEARCH,
        resolved_params={"dataset": StringValue(value="pfal3D7_Sexual_Stage_rnaSeq")},
    )


def _built() -> tuple[OperationalSpec, StrategySession]:
    spec = OperationalSpec(
        goal="genes upregulated in gametocytes",
        criteria=[_carrier()],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=_CRITERION)
        ),
    )
    tree = build_step_tree(spec)
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="gametocytes", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    step_id = next(iter(graph.steps))
    session.sync_state = WDKSyncState(
        wdk_step_ids={step_id: 11},
        step_counts={step_id: _WRITTEN_THROUGH},
        wdk_strategy_id=900,
    )
    return renumber_criteria(spec, tree.step_id_by_criterion), session


async def _edited_outcome(monkeypatch: pytest.MonkeyPatch) -> BuildOutcome:
    """Run one edit whose commit is a capture, and return the build it records."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    state = pipeline_state(
        user_prompt="use the sexual stage dataset",
        domain=StrategyDomainState(operational_spec=before.model_copy(deep=True)),
    )
    state.domain.spec_before_turn = before
    deps = lead_deps(state, strategy_session=session)

    async def _fake_frame(**_kwargs: Any) -> FrameResult:
        state.domain.operational_spec = after
        return FrameResult(disposition="spec_ready", summary="reframed")

    async def _fake_commit(**_kwargs: Any) -> CommitResult:
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "run_frame", _fake_frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _fake_commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)

    await run_edit(deps=deps, parent_tool_call_id="t1", reason="new dataset")
    outcome = deps.state.domain.last_build_outcome
    assert outcome is not None
    return outcome


@pytest.mark.asyncio
async def test_the_reported_count_is_the_one_the_commit_wrote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = await _edited_outcome(monkeypatch)

    assert set(outcome.counts.values()) == {_WRITTEN_THROUGH}


@pytest.mark.asyncio
async def test_the_root_reports_that_count_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = await _edited_outcome(monkeypatch)

    assert outcome.root_count == _WRITTEN_THROUGH
