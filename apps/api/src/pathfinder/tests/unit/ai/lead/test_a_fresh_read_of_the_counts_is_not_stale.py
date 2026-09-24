"""A resync or a build reads the counts afresh, so the build is no longer stale."""

from __future__ import annotations

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.turn_budget import budget_stop_report
from pathfinder.domain.strategy.staleness import StaleBuild
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    STEP,
    STRATEGY_LINE,
    built_outcome,
    built_session,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state


def _stale_state() -> PipelineState:
    return pipeline_state(
        user_prompt="recover the failed step",
        domain=StrategyDomainState(
            last_build_outcome=built_outcome(),
            stale_build=StaleBuild(changed_nodes=[(STEP, 70, 12)]),
        ),
    )


def _stale_lines(state: PipelineState) -> list[str]:
    summary = derive_ledger(state, None).render_summary()
    return [line for line in summary.splitlines() if "STALE" in line]


def _strategy_paragraph(state: PipelineState) -> str:
    report = budget_stop_report(
        derive_ledger(state, None), built_session(), TurnMarkers(), []
    )
    return report.split("\n\n")[0]


def test_the_stale_state_prints_the_marker_before_any_read() -> None:
    state = _stale_state()

    assert len(_stale_lines(state)) == 1
    assert _strategy_paragraph(state) != STRATEGY_LINE


def test_a_resync_supersedes_the_staleness_it_read_past() -> None:
    state = _stale_state()

    state.record_resync(built_outcome())

    assert state.domain.stale_build is None
    assert _stale_lines(state) == []
    assert _strategy_paragraph(state) == STRATEGY_LINE
    assert state.turn_markers.built is False


def test_a_build_supersedes_the_staleness_and_marks_the_turn_built() -> None:
    state = _stale_state()

    state.record_build(built_outcome())

    assert state.domain.stale_build is None
    assert _stale_lines(state) == []
    assert _strategy_paragraph(state) == STRATEGY_LINE
    assert state.turn_markers.built is True
