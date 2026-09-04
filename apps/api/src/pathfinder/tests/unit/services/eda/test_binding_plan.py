"""Which binding a revert must leave, read from the log and the row on disk."""

from __future__ import annotations

from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.persistence.models import ConversationAnalysisView
from pathfinder.services.eda.thread_surgery import (
    AdoptBinding,
    DropBinding,
    KeepBinding,
    binding_plan,
)

_DATASET = "DS_1234567890"


def _recorded(analysis_id: str) -> EdaAnalysisState:
    return EdaAnalysisState(
        site_id="plasmodb",
        dataset_id=_DATASET,
        study_id="STUDY_1234567890",
        analysis_id=analysis_id,
        revision=2,
        study_display_name="Gametocyte panel",
        display_name="gametocyte rows",
        num_filters=0,
        num_computations=0,
        filters=[],
        filter_summaries=[],
        entity_counts=[],
        can_export_rows=True,
    )


def _bound(analysis_id: str) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=_DATASET,
        analysis_id=analysis_id,
        revision=3,
    )


def test_a_log_with_no_analysis_state_and_no_row_leaves_the_thread_unbound() -> None:
    assert binding_plan(recorded=None, bound=None, logged=False) == KeepBinding()


def test_a_log_that_recorded_a_binding_drops_the_row_the_cut_orphaned() -> None:
    plan = binding_plan(recorded=None, bound=_bound("a1b2c3d4"), logged=True)

    assert plan == DropBinding()


def test_a_binding_the_log_never_recorded_is_left_alone() -> None:
    """A study opened from the tab alone leaves no part, so the log is silent."""
    plan = binding_plan(recorded=None, bound=_bound("a1b2c3d4"), logged=False)

    assert plan == KeepBinding()


def test_the_row_naming_the_recorded_analysis_keeps_that_document() -> None:
    recorded = _recorded("a1b2c3d4")

    plan = binding_plan(recorded=recorded, bound=_bound("a1b2c3d4"), logged=True)

    assert plan == AdoptBinding(recorded=recorded, rebind=False)


def test_a_row_naming_another_analysis_rebinds_to_the_recorded_one() -> None:
    recorded = _recorded("a1b2c3d4")

    plan = binding_plan(recorded=recorded, bound=_bound("z9y8x7w6"), logged=True)

    assert plan == AdoptBinding(recorded=recorded, rebind=True)


def test_a_recorded_state_with_no_row_rebinds() -> None:
    recorded = _recorded("a1b2c3d4")

    assert binding_plan(recorded=recorded, bound=None, logged=True) == AdoptBinding(
        recorded=recorded,
        rebind=True,
    )
