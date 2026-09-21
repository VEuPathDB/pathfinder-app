"""The ways a thread's spec and its strategy differ when an edit starts.

Each test sets the two apart the way one event does, runs the pre-turn refresh
and the edit dispatch, and states what the strategy holds afterwards.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    CANVAS,
    PROTEOME,
    tree_with_the_canvas_step,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_TIMEPOINT,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
    surface_step,
)

_OPTION = "c_stage_dataset"


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


async def _left_with_an_open_criterion(thread: DisagreementThread) -> None:
    await thread.next_turn()
    thread.frames(with_the_proteome(None), declared=[], disposition="needs_user")
    await thread.edit()


async def test_a_criterion_framed_last_turn_is_built_this_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await _left_with_an_open_criterion(thread)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, PROTEOME))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [op.kind for op in thread.committed] == ["addLeaf", "addCombine"]
    await thread.next_turn()
    assert thread.criteria == [SURFACE, STAGE, PROTEOME]


async def test_a_step_added_in_the_editor_is_stated_and_survives_an_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(tree_with_the_canvas_step()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    thread.frames(with_the_percentile(90), declared=[])

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.criteria == [SURFACE, STAGE, CANVAS]
    assert [op.kind for op in thread.committed] == ["updateStepParams"]
    assert CANVAS in thread.graph.steps


async def test_an_editor_step_beside_an_unbuilt_criterion_is_refused_not_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refresh leaves a plan alone, so the edit meets a step nothing states."""
    thread = _thread(monkeypatch)
    await _left_with_an_open_criterion(thread)
    thread.session.graph = session_holding(tree_with_the_canvas_step()).graph
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, PROTEOME))

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert CANVAS in refusal
    assert thread.committed == []
    assert CANVAS in thread.graph.steps


def _stating_the_canvas_step() -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        found = with_the_proteome(2)(found)
        found.criteria.append(
            Criterion(id=CANVAS, text="added in the editor", search_name="GenesByTaxon")
        )
        found.structure = SpecStructure(
            root=joined(
                CombineOp.INTERSECT,
                joined(
                    CombineOp.INTERSECT,
                    joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(STAGE)),
                    leaf(CANVAS),
                ),
                leaf(PROTEOME),
            )
        )
        return found

    return _draft


async def test_stating_the_editor_step_is_the_way_out_of_that_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await _left_with_an_open_criterion(thread)
    thread.session.graph = session_holding(tree_with_the_canvas_step()).graph
    await thread.next_turn()
    thread.frames(_stating_the_canvas_step(), declared=kept(SURFACE, STAGE, PROTEOME))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [op.kind for op in thread.committed] == ["addLeaf", "addCombine"]
    assert CANVAS in thread.graph.steps


async def test_a_step_deleted_in_the_editor_leaves_and_the_open_one_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await _left_with_an_open_criterion(thread)
    thread.session.graph = session_holding(surface_step()).graph
    await thread.next_turn()
    assert thread.criteria == [SURFACE, PROTEOME]
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, PROTEOME))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [op.kind for op in thread.committed] == ["addLeaf", "addCombine"]
    assert STAGE not in thread.graph.steps


def _with_the_option(value: str | None) -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [c for c in found.criteria if c.id != _OPTION]
        found.criteria.append(
            Criterion(
                id=_OPTION,
                text="read the 2019 dataset",
                search_name="GenesByRNASeqEvidence",
                resolved_params={}
                if value is None
                else {"dataset": StringValue(value=value)},
                open_params=[]
                if value is not None
                else [OpenSlot(criterion_id=_OPTION, param_name="dataset")],
            )
        )
        return found

    return _draft


async def test_an_option_framed_last_turn_lands_on_the_step_that_runs_its_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(_with_the_option(None), declared=[], disposition="needs_user")
    await thread.edit()
    await thread.next_turn()
    thread.frames(_with_the_option("ds2019"), declared=kept(SURFACE, STAGE, _OPTION))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [op.kind for op in thread.committed] == ["updateStepParams"]
    assert thread.graph.steps[STAGE].parameters["dataset"] == StringValue(
        value="ds2019"
    )
    assert sorted(thread.graph.steps) == sorted([SURFACE, STAGE, ROOT])


async def test_a_value_set_in_the_editor_survives_an_edit_that_names_another_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] = NumberValue(value=48)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] == NumberValue(
        value=48
    )
