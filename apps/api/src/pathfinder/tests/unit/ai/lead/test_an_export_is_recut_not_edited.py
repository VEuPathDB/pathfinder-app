"""An analysis export is recut by create_eda_step, never by an edit: FRAME binds
no export's cut."""

from __future__ import annotations

import pytest

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.tools.standalone.eda_step import create_eda_step
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.tests._support.eda_step_doubles import DE_DATASET, export_step
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
    stage = thread.graph.steps[STAGE]
    assert stage.search_name is not None
    document = export_step(STAGE, DE_DATASET).parameters
    thread.graph.steps[STAGE] = stage.model_copy(
        update={"parameters": {**stage.parameters, **document}}
    )
    thread.graph.note_analysis_kinds(
        {STAGE: StampedKind(search_name=stage.search_name, kind=AnalysisKind.COMPUTE)}
    )
    thread.deps.state.domain.open_eda_analysis = OpenEdaAnalysis(
        dataset_id=DE_DATASET, analysis_id="an_open_analysis"
    )
    thread.frames(_unchanged)

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.committed == []
    assert delta.description == (
        "The edit changes no step FRAME binds: FRAME keeps an analysis export as it "
        f"is. A change to the export's thresholds or direction is create_eda_step("
        f"replace_step_id='{STAGE}'), which reads the completed compute again; new "
        "groups run run_eda_compute first. That recut is the change the researcher "
        "asked for, so it needs no card: make it. Any other request the strategy "
        "already states."
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
        "``edit_strategy``:"
    ) in read


def test_the_instruction_and_the_tool_name_the_recut_of_an_export() -> None:
    """Neither scopes ``replace_step_id`` to steps that leave out the recut."""
    read = " ".join(LEAD_INSTRUCTIONS.split())
    described = " ".join((create_eda_step.__doc__ or "").split())

    assert [
        (
            "Pass ``replace_step_id`` to put the export in the place of a step "
            "the strategy holds: an export of the open analysis whose cut changes, "
            "an EDA-backed step built without an analysis, or a step this subset "
            "supersedes."
        )
        in read,
        (
            "new thresholds or a new direction read the completed compute again, "
            "and new groups run ``run_eda_compute`` first. That recut is the change "
            "the researcher asked for, so it needs no card: make it."
        )
        in read,
        (
            "Use it to recut an export of the open analysis: new thresholds or a new "
            "direction read the completed compute again, and new groups run "
            "``run_eda_compute`` first. That recut is the change the researcher "
            "asked for, so it needs no card."
        )
        in described,
    ] == [True, True, True]
