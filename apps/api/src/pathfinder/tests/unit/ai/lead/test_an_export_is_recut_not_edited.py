"""An analysis export is recut by create_eda_step, never by an edit: FRAME binds
no export's cut."""

from __future__ import annotations

import pytest

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    NESTED_ROOT,
    THIRD,
    nested_spec,
    nested_tree,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    SURFACE,
    DisagreementThread,
    recorded,
    session_holding,
)


def _unchanged(found: OperationalSpec) -> OperationalSpec:
    return found


async def test_an_edit_that_moves_nothing_names_the_recut_of_an_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = DisagreementThread(
        monkeypatch,
        spec=nested_spec(),
        session=session_holding(nested_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT, THIRD, NESTED_ROOT),
    )
    await thread.next_turn()
    search_name = thread.graph.steps[STAGE].search_name
    assert search_name is not None
    thread.graph.note_analysis_kinds(
        {STAGE: StampedKind(search_name=search_name, kind=AnalysisKind.COMPUTE)}
    )
    thread.frames(_unchanged)

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.committed == []
    assert delta.description == (
        "The edit changes no step FRAME binds. A change to an analysis export's cut "
        f"is create_eda_step(replace_step_id='{STAGE}') with the new thresholds, "
        "direction or groups; any other request the strategy already states."
    )


async def test_an_edit_that_moves_nothing_without_an_export_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = DisagreementThread(
        monkeypatch,
        spec=nested_spec(),
        session=session_holding(nested_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT, THIRD, NESTED_ROOT),
    )
    await thread.next_turn()
    thread.frames(_unchanged)

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert (
        delta.description == "The strategy already states everything the edit asks for."
    )


def test_the_lead_recuts_an_export_with_create_eda_step() -> None:
    read = " ".join(LEAD_INSTRUCTIONS.split())

    assert (
        "A change to an exported step's thresholds, direction or groups is "
        "``create_eda_step`` with ``replace_step_id`` set to that step, never "
        "``edit_strategy``."
    ) in read
