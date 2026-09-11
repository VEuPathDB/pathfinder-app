"""What an EDA export leaves behind: the parts it emits and the build it records."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext

from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.eda_doubles import ANALYSIS_ID, lead_run_context
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    WDK_STRATEGY_ID,
    bound,
    pushing_commit,
    read_detail,
    read_detail_with_computation,
    recording_commit,
)


@pytest.fixture
def lead_ctx() -> RunContext[LeadDeps]:
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("g1", "Test", "plasmodb"))
    return lead_run_context(prompt="export the febrile subset", session=session)


def _wire(monkeypatch: pytest.MonkeyPatch, *, read: object, commit: object) -> None:
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read)
    monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)


async def test_the_step_emits_the_parts_the_workbench_already_listens_to(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, read=read_detail, commit=recording_commit([]))

    returned = await eda_step.create_eda_step(lead_ctx)

    kinds = [c.type for c in returned.metadata]
    assert "data-graph-snapshot" in kinds
    assert "data-strategy-link" not in kinds


async def test_a_commit_with_a_wdk_url_also_emits_the_strategy_link(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(
        monkeypatch,
        read=read_detail,
        commit=recording_commit(
            [], wdk_url="https://plasmodb.org/plasmo/app/workspace"
        ),
    )

    returned = await eda_step.create_eda_step(lead_ctx)

    kinds = [c.type for c in returned.metadata]
    assert kinds == ["data-graph-snapshot", "data-strategy-link"]
    assert returned.return_value.wdk_strategy_id == WDK_STRATEGY_ID


async def test_a_step_wdk_rejected_is_reported_rather_than_hidden(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The commit reports a rejection on the step; the model must see it."""

    async def commit(*, deps: object, ops: list[Any]) -> CommitResult:
        del deps, ops
        return CommitResult(description="added", failed_step_ids=["step_1"])

    _wire(monkeypatch, read=read_detail, commit=commit)

    returned = await eda_step.create_eda_step(lead_ctx)

    assert returned.return_value.failed_step_ids == ["step_1"]
    assert returned.return_value.wdk_strategy_id is None


async def test_the_export_records_the_build_the_turn_left(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The exported step is a built step, so the turn records a build outcome."""
    session = lead_ctx.deps.runtime.strategy_session
    _wire(
        monkeypatch,
        read=read_detail,
        commit=pushing_commit([], session=session, count=1543),
    )

    returned = await eda_step.create_eda_step(lead_ctx)

    step_id = returned.return_value.step_id
    state = lead_ctx.deps.state
    outcome = state.domain.last_build_outcome
    assert outcome is not None
    assert outcome.root_count == 1543
    assert outcome.pushed_step_ids == [step_id]
    assert outcome.wdk_strategy_id == WDK_STRATEGY_ID
    assert [n.node_id for n in outcome.node_results] == [step_id]
    assert outcome.node_results[0].wdk_step_id == 8811
    assert outcome.node_results[0].status == "ok"
    assert state.turn_markers.built is True
    ledger = derive_ledger(state, None)
    assert ledger.build.pushed_count == 1
    assert ledger.build.succeeded is True
    assert "root_count: 1543" in ledger.render_section("build")


async def test_the_export_records_what_the_case_remembers(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The cut the turn exported, kept for the case the turn leaves behind."""
    session = lead_ctx.deps.runtime.strategy_session
    _wire(
        monkeypatch,
        read=read_detail_with_computation,
        commit=pushing_commit([], session=session, count=212),
    )

    returned = await eda_step.create_eda_step(
        lead_ctx,
        effect_size_threshold=1.5,
        significance_threshold=0.01,
        effect_direction="upOnly",
    )

    export = lead_ctx.deps.state.turn_markers.eda_export
    assert export is not None
    assert export.dataset_id == PHENOTYPE_DATASET
    assert export.analysis_id == ANALYSIS_ID
    assert export.search_name == "GenesByEdaVizWithCompute"
    assert export.step_id == returned.return_value.step_id
    assert export.is_compute_backed is True
    assert export.effect_size_threshold == 1.5
    assert export.significance_threshold == 0.01
    assert export.effect_direction == "upOnly"


async def test_a_zero_count_export_is_recorded_as_a_zero_step(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """An export that selects nothing is a zero-result step, not a silent one."""
    session = lead_ctx.deps.runtime.strategy_session
    _wire(
        monkeypatch,
        read=read_detail,
        commit=pushing_commit([], session=session, count=0),
    )

    returned = await eda_step.create_eda_step(lead_ctx)

    outcome = lead_ctx.deps.state.domain.last_build_outcome
    assert outcome is not None
    assert outcome.root_count == 0
    assert outcome.zero_step_ids == [returned.return_value.step_id]


async def test_a_draft_export_the_site_never_took_records_no_build(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A step that did not reach VEuPathDB has no size, so nothing is built."""

    async def commit(*, deps: object, ops: list[Any]) -> CommitResult:
        del deps
        graph = lead_ctx.deps.runtime.strategy_session.get_graph(None)
        assert graph is not None
        apply_operation(graph, ops[0])
        return CommitResult(description="added a draft step")

    _wire(monkeypatch, read=read_detail, commit=commit)

    await eda_step.create_eda_step(lead_ctx)

    state = lead_ctx.deps.state
    assert state.domain.last_build_outcome is None
    assert state.turn_markers.built is False
