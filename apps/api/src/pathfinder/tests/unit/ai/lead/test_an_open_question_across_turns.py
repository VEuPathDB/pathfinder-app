"""An edit that stops on the user, and the turn that answers it.

A ``needs_user`` pass commits its draft as the thread's spec without pushing
anything, so the follow-up plans against a spec the strategy has not reached.
Each test states what the follow-up commits and what the delta reports.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    structure_criteria,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    PROTEOME_PARAM,
    canvas_deletes,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import (
    OpFacts,
    committed_facts,
    spec_facts,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_PERCENTILE,
    STAGE_TIMEPOINT,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    declared,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)

_LOCALISED = "c_apicoplast"
_LOCALISED_PARAM = "compartment"


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _localised(value: float | None) -> Criterion:
    return Criterion(
        id=_LOCALISED,
        text="localised to the apicoplast",
        search_name="GenesByLocalisation",
        resolved_params={}
        if value is None
        else {_LOCALISED_PARAM: NumberValue(value=value)},
        open_params=[]
        if value is not None
        else [OpenSlot(criterion_id=_LOCALISED, param_name=_LOCALISED_PARAM)],
    )


def _with_both_open(proteome: float | None, localised: float | None) -> Draft:
    """Two new criteria at the root, each open until its own turn answers it."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found = with_the_proteome(proteome)(found)
        found.criteria = [c for c in found.criteria if c.id != _LOCALISED]
        found.criteria.append(_localised(localised))
        assert found.structure is not None
        if _LOCALISED not in structure_criteria(found.structure):
            found.structure = SpecStructure(
                root=joined(CombineOp.INTERSECT, found.structure.root, leaf(_LOCALISED))
            )
        return found

    return _draft


def _dropping_the_stage_and_asking() -> Draft:
    """The pass drops a built criterion and asks one question in the same breath."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found = with_the_proteome(None)(found)
        found.criteria = [c for c in found.criteria if c.id != STAGE]
        found.structure = SpecStructure(
            root=joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(PROTEOME))
        )
        return found

    return _draft


def _a_different_request() -> Draft:
    """The user asked for something else, so the open criterion is abandoned."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found = with_the_percentile(90)(found)
        found.criteria = [c for c in found.criteria if c.id != PROTEOME]
        found.structure = built_spec().structure
        return found

    return _draft


async def _asked(
    thread: DisagreementThread,
    draft: Draft,
    account: list[CriterionChange] | None = None,
) -> None:
    """Run the turn that ends on the user, and check it pushed nothing."""
    await thread.next_turn()
    thread.frames(draft, declared=account or [], disposition="needs_user")
    delta = await thread.edit()
    assert isinstance(delta, EditDelta)
    assert delta.disposition == "needs_user"
    assert thread.committed == []


async def test_a_dropped_criterion_beside_an_open_question_leaves_the_follow_up_stuck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The drop was never pushed, and the answering turn is refused by the step it left."""
    thread = _thread(monkeypatch)
    await _asked(thread, _dropping_the_stage_and_asking(), declared("dropped", STAGE))
    await thread.next_turn()
    assert thread.criteria == [SURFACE, PROTEOME]
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, PROTEOME))

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert f"the edit would take ['{STAGE}'] off the strategy" in refusal
    assert "the edited spec states no drop for them" in refusal
    assert thread.committed == []
    assert thread.graph.steps[STAGE].parameters[STAGE_PERCENTILE] == NumberValue(
        value=80
    )


async def test_two_open_questions_answered_one_a_turn_build_on_the_third(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turn two pushes nothing; turn three builds both criteria at once."""
    thread = _thread(monkeypatch)
    await _asked(thread, _with_both_open(None, None))
    await thread.next_turn()
    thread.frames(_with_both_open(2, None), declared=[], disposition="needs_user")
    second = await thread.edit()
    assert isinstance(second, EditDelta)
    assert (second.disposition, second.operations_applied) == ("needs_user", 0)
    await thread.next_turn()
    thread.frames(
        _with_both_open(2, 7), declared=kept(SURFACE, STAGE, PROTEOME, _LOCALISED)
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert delta.disposition == "applied"
    assert [op.kind for op in committed_facts(thread.committed)] == [
        "addLeaf",
        "addCombine",
        "addLeaf",
        "addCombine",
    ]
    assert spec_facts(thread.spec) == {
        SURFACE: {},
        STAGE: {STAGE_PERCENTILE: "80", STAGE_TIMEPOINT: "40"},
        PROTEOME: {PROTEOME_PARAM: "2"},
        _LOCALISED: {_LOCALISED_PARAM: "7"},
    }
    assert sorted(delta.added_step_ids) == sorted([PROTEOME, _LOCALISED])
    assert sorted(delta.preserved_step_ids) == sorted([SURFACE, STAGE])


async def test_a_different_request_instead_of_an_answer_abandons_the_open_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The open criterion never reached a step, so dropping it costs no operation."""
    thread = _thread(monkeypatch)
    await _asked(thread, with_the_proteome(None))
    await thread.next_turn()
    thread.frames(
        _a_different_request(),
        declared=[
            *kept(SURFACE),
            *declared("changed", STAGE),
            *declared("dropped", PROTEOME),
        ],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == [
        OpFacts(
            kind="updateStepParams",
            step_id=STAGE,
            parameters={STAGE_PERCENTILE: "90"},
        )
    ]
    assert thread.criteria == [SURFACE, STAGE]
    assert thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] == NumberValue(
        value=40
    )
    assert delta.diff.dropped_count == 1
    assert delta.diff.changed_count == 1


async def test_a_canvas_delete_before_the_answer_takes_the_step_and_keeps_the_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deleted criterion leaves the spec; the open one is built on what is left."""
    thread = _thread(monkeypatch)
    await _asked(thread, with_the_proteome(None))
    canvas_deletes(thread.graph, STAGE)
    await thread.next_turn()
    assert thread.criteria == [SURFACE, PROTEOME]
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, PROTEOME))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [(op.kind, op.step_id) for op in committed_facts(thread.committed)] == [
        ("addLeaf", PROTEOME),
        ("addCombine", _root_of(thread)),
    ]
    assert sorted(thread.graph.steps) == sorted([SURFACE, PROTEOME, _root_of(thread)])
    assert spec_facts(thread.spec) == {SURFACE: {}, PROTEOME: {PROTEOME_PARAM: "2"}}


def _root_of(thread: DisagreementThread) -> str:
    root = thread.graph.primary_root_id()
    assert root is not None
    return root
