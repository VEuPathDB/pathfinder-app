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
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.build_outcome import BuiltCounts, built_counts
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_tree import (
    build_step_tree,
    renumber_criteria,
)
from pathfinder.services.strategies import data_marks
from pathfinder.services.strategies.commit import CommitResult, live_strategy_url
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SEARCH = "GenesByRNASeqEvidence"
_CRITERION = "gametocyte_expression"
_WRITTEN_THROUGH = 71


def _carrier() -> Criterion:
    return Criterion(
        id=_CRITERION,
        text="upregulated in gametocytes",
        search_name=_SEARCH,
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=["Pf3D7"]),
                "dataset": StringValue(value="all_rnaseq"),
            },
            defaulted=["dataset"],
        ),
    )


def _option() -> Criterion:
    return Criterion(
        id="sexual_stage_option",
        text="use the sexual stage dataset",
        search_name=_SEARCH,
        resolved_params=bound(
            {"dataset": StringValue(value="pfal3D7_Sexual_Stage_rnaSeq")}
        ),
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
        wdk_step_tree=WDKStepTree(step_id=11),
    )
    return renumber_criteria(spec, tree.step_id_by_criterion), session


async def _edited(monkeypatch: pytest.MonkeyPatch, *, arrived: int = 0) -> LeadDeps:
    """Run one edit whose commit is a capture, on a message that found the
    root at ``arrived`` genes."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    state = pipeline_state(
        user_prompt="use the sexual stage dataset",
        domain=StrategyDomainState(operational_spec=before.model_copy(deep=True)),
    )
    state.domain.spec_before_turn = before
    deps = lead_deps(state, strategy_session=session)
    root = next(iter(session.graph.steps)) if session.graph is not None else ""
    deps.state.turn_markers.record_arrival(root, {root: arrived})

    async def _fake_frame(**_kwargs: Any) -> FrameResult:
        state.domain.operational_spec = after
        return FrameResult(disposition="spec_ready", summary="reframed")

    async def _fake_commit(**_kwargs: Any) -> CommitResult:
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "run_frame", _fake_frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _fake_commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)

    await run_edit(deps=deps, parent_tool_call_id="t1", reason="new dataset")
    return deps


async def _edited_counts(monkeypatch: pytest.MonkeyPatch) -> BuiltCounts:
    """The counts the session holds after the edit, once the edit recorded its build."""
    deps = await _edited(monkeypatch)
    session = deps.runtime.strategy_session
    assert deps.state.domain.last_build_outcome is not None
    return built_counts(session.graph, session.sync_state)


@pytest.mark.asyncio
async def test_the_reported_count_is_the_one_the_commit_wrote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = await _edited_counts(monkeypatch)

    assert set(counts.by_step.values()) == {_WRITTEN_THROUGH}


@pytest.mark.asyncio
async def test_the_root_reports_that_count_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = await _edited_counts(monkeypatch)

    assert counts.root_count == _WRITTEN_THROUGH


@pytest.mark.asyncio
async def test_an_edit_that_leaves_the_tree_in_place_keeps_the_strategy_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = await _edited(monkeypatch)

    assert live_strategy_url("plasmodb", deps.runtime.strategy_session.sync_state) == (
        "https://plasmodb.org/plasmo/app/workspace/strategies/900/11"
    )


@pytest.mark.asyncio
async def test_the_root_s_count_before_the_edit_is_its_count_at_arrival(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The edit records no count of its own; the facts read the strategy the
    message found."""
    deps = await _edited(monkeypatch, arrived=80)

    facts = turn_facts(deps)
    assert (facts.root_count, facts.root_count_before) == (_WRITTEN_THROUGH, 80)


@pytest.mark.asyncio
async def test_an_edit_reads_the_assay_of_each_search_it_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A data-type requirement grounds against the strategy the edit wrote."""

    async def _assay(_site: str, search_name: str) -> str | None:
        return "RNASeq" if search_name == _SEARCH else None

    monkeypatch.setattr(data_marks, "dataset_assay", _assay)

    deps = await _edited(monkeypatch)

    assert deps.state.domain.data_marks.searches == {_SEARCH: "RNASeq"}
