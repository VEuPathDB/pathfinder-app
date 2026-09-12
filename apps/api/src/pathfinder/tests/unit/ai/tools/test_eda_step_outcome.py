"""What an EDA export leaves behind: the parts it emits and the build it records."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb_mcp import ToolErrorPayload

from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.build_outcome import StepPushFailure
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.eda_doubles import ANALYSIS_ID
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
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
    return lead_run_context(
        user_prompt="export the febrile subset", strategy_session=session
    )


def _wire(monkeypatch: pytest.MonkeyPatch, *, read: object, commit: object) -> None:
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read)
    monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)


async def test_the_step_emits_the_parts_the_workbench_already_listens_to(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, read=read_detail, commit=recording_commit([]))

    answer = await eda_step.create_eda_step(lead_ctx)

    kinds = [c.type for c in answer.metadata]
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

    answer = await eda_step.create_eda_step(lead_ctx)

    kinds = [c.type for c in answer.metadata]
    assert kinds == ["data-graph-snapshot", "data-strategy-link"]
    result = returned(answer, eda_step.EdaStepCreated)
    assert result.wdk_strategy_id == WDK_STRATEGY_ID


def _refusing_commit(status: int | None) -> Any:
    async def commit(*, deps: object, ops: list[Any]) -> CommitResult:
        del deps, ops
        return CommitResult(
            description="added",
            failures=[
                StepPushFailure(
                    step_id="step_1",
                    search_name="EdaSubsettingStep",
                    error="WDK refused the analysis spec",
                    wdk_status=status,
                )
            ],
        )

    return commit


async def test_a_step_wdk_refused_is_retried_with_wdks_message(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A refusal of the values is a retry, not a step the answer calls added."""
    _wire(monkeypatch, read=read_detail, commit=_refusing_commit(422))

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx)

    assert "WDK refused the analysis spec" in str(excinfo.value)


async def test_a_step_the_site_never_took_answers_with_the_error(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """An answer a retry cannot mend is the tool's error, not a success model."""
    _wire(monkeypatch, read=read_detail, commit=_refusing_commit(None))

    answer = await eda_step.create_eda_step(lead_ctx)

    error = returned(answer, ToolErrorPayload)
    assert error.code == ErrorCode.WDK_ERROR.value
    assert "WDK refused the analysis spec" in error.message


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

    answer = await eda_step.create_eda_step(lead_ctx)

    result = returned(answer, eda_step.EdaStepCreated)
    step_id = result.step_id
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

    answer = await eda_step.create_eda_step(
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
    result = returned(answer, eda_step.EdaStepCreated)
    assert export.step_id == result.step_id
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

    answer = await eda_step.create_eda_step(lead_ctx)

    outcome = lead_ctx.deps.state.domain.last_build_outcome
    assert outcome is not None
    assert outcome.root_count == 0
    result = returned(answer, eda_step.EdaStepCreated)
    assert outcome.zero_step_ids == [result.step_id]


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
