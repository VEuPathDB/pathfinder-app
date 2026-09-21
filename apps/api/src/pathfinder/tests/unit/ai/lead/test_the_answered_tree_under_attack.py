"""Outside changes the answered tree must see, and the edit that follows each."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.operational_spec import (
    AssumedValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    NESTED_ROOT,
    PROTEOME,
    THIRD,
    canvas_flips,
    canvas_sets,
    nested_spec,
    nested_tree,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import OpFacts, committed_facts
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
    stage_step,
)

READDED = "step_5a6b7c8d"
RING = "c_ring_stage"


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _only_the_percentile(delta: EditDelta | str, thread: DisagreementThread) -> None:
    assert isinstance(delta, EditDelta), delta
    assert committed_facts(thread.committed) == [
        OpFacts(
            kind="updateStepParams",
            step_id=_stage_id(thread),
            parameters={STAGE_PERCENTILE: "90"},
        )
    ]


def _stage_id(thread: DisagreementThread) -> str:
    return READDED if READDED in thread.graph.steps else STAGE


def _percentile_on(step_id: str) -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        for criterion in found.criteria:
            if criterion.id == step_id:
                criterion.resolved_params = {
                    **criterion.resolved_params,
                    STAGE_PERCENTILE: NumberValue(value=90),
                }
        return found

    return _draft


async def test_a_step_deleted_and_added_again_with_the_same_search_is_a_new_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two trees hash alike, and the step the spec addressed is gone."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    again = built_tree().model_copy(
        update={"secondary_input": stage_step().model_copy(update={"id": READDED})}
    )
    readded = session_holding(again).get_graph(None)
    assert readded is not None
    thread.graph.steps = readded.steps
    thread.graph.recompute_roots()

    await thread.next_turn()

    assert thread.criteria == [SURFACE, READDED]
    assert [c.id for c in thread.answered.criteria] == [SURFACE, READDED]
    thread.frames(_percentile_on(READDED), declared=kept(SURFACE))
    _only_the_percentile(await thread.edit(), thread)


async def test_the_inputs_of_the_root_swapped_on_the_canvas_stand_through_an_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    root = thread.graph.steps[ROOT]
    root.primary_input_id, root.secondary_input_id = STAGE, SURFACE

    await thread.next_turn()

    assert thread.spec.structure == SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(STAGE), leaf(SURFACE))
    )
    thread.frames(with_the_percentile(90), declared=kept(SURFACE))
    _only_the_percentile(await thread.edit(), thread)
    assert thread.graph.steps[ROOT].primary_input_id == STAGE


async def test_a_strategy_emptied_outside_leaves_every_spec_stating_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.graph.steps.clear()
    thread.graph.recompute_roots()

    await thread.next_turn()

    domain = thread.deps.state.domain
    assert [c.id for c in thread.spec.criteria] == []
    assert domain.answered_spec is None or domain.answered_spec.criteria == []
    assert domain.answered_graph is None


async def test_one_join_of_a_flat_three_way_combine_flipped_on_the_canvas_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The spec states one combine over three criteria; the tree holds two."""
    spec = nested_spec()
    spec.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(STAGE), leaf(THIRD))
    )
    thread = DisagreementThread(
        monkeypatch,
        spec=spec,
        session=session_holding(nested_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT, THIRD, NESTED_ROOT),
    )
    await thread.next_turn()
    canvas_flips(thread.graph, ROOT, CombineOp.UNION)

    await thread.next_turn()

    assert thread.spec.structure == SpecStructure(
        root=joined(
            CombineOp.INTERSECT,
            joined(CombineOp.UNION, leaf(SURFACE), leaf(STAGE)),
            leaf(THIRD),
        )
    )
    thread.frames(with_the_percentile(90), declared=kept(SURFACE, THIRD))
    _only_the_percentile(await thread.edit(), thread)
    assert thread.graph.steps[ROOT].operator == CombineOp.UNION


def _carrying_the_ring_option() -> OperationalSpec:
    """The built spec whose stage criterion carries an option's timepoint."""
    spec = built_spec()
    for criterion in spec.criteria:
        if criterion.id == STAGE:
            criterion.assumptions = [
                AssumedValue(
                    param_name=STAGE_TIMEPOINT,
                    value="40",
                    reason="ring stage",
                    carried_from=RING,
                )
            ]
    return spec


def _asking_for_the_ring_stage_again(found: OperationalSpec) -> OperationalSpec:
    found.criteria.append(
        Criterion(
            id=RING,
            text="ring stage",
            search_name="GenesByRNASeqEvidence",
            resolved_params={STAGE_TIMEPOINT: NumberValue(value=40)},
        )
    )
    return found


async def test_an_option_restating_the_value_the_canvas_replaced_is_pushed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The carried value retired with the canvas edit, so the option moves it back."""
    thread = DisagreementThread(
        monkeypatch,
        spec=_carrying_the_ring_option(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    canvas_sets(thread.graph, STAGE, **{STAGE_TIMEPOINT: NumberValue(value=48)})
    await thread.next_turn()
    assert [a.param_name for c in thread.spec.criteria for a in c.assumptions] == []
    thread.frames(_asking_for_the_ring_stage_again, declared=kept(SURFACE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert committed_facts(thread.committed) == [
        OpFacts(
            kind="updateStepParams",
            step_id=STAGE,
            parameters={STAGE_TIMEPOINT: "40"},
        )
    ]
    assert thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] == NumberValue(
        value=40
    )


async def test_a_turn_that_resumes_with_no_parked_dispatch_replays_every_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A finished background task re-enters the turn; no dispatch reconciles it."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.deps.state.domain.spec_before_dispatch = thread.spec.model_copy(deep=True)
    canvas_sets(thread.graph, STAGE, **{STAGE_TIMEPOINT: NumberValue(value=48)})

    await thread.next_turn(resumes_parked_call=True)

    domain = thread.deps.state.domain
    held = {
        "plan": domain.operational_spec,
        "answer": domain.answered_spec,
        "turn": domain.spec_before_turn,
        "dispatch": domain.spec_before_dispatch,
    }
    timepoints = {
        name: next(c for c in spec.criteria if c.id == STAGE).resolved_params[
            STAGE_TIMEPOINT
        ]
        for name, spec in held.items()
        if spec is not None
    }
    assert timepoints == dict.fromkeys(held, NumberValue(value=48))
    assert thread.ledger_diff().touched_count() == 0


def _dropping_the_stage_and_asking(found: OperationalSpec) -> OperationalSpec:
    found = with_the_proteome(None)(found)
    found.criteria = [c for c in found.criteria if c.id != STAGE]
    found.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(PROTEOME))
    )
    return found


def _taking_the_question_back(found: OperationalSpec) -> OperationalSpec:
    found.criteria = [c for c in found.criteria if c.id != PROTEOME]
    found.structure = SpecStructure(root=leaf(SURFACE))
    return found


async def test_a_drop_no_pass_of_this_turn_declared_is_not_pushed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workspace never showed the pass the step an earlier draft dropped."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _dropping_the_stage_and_asking,
        declared=declared("dropped", STAGE),
        disposition="needs_user",
    )
    await thread.edit()
    await thread.next_turn()
    thread.frames(
        _taking_the_question_back,
        declared=[*kept(SURFACE), *declared("dropped", PROTEOME)],
    )

    await thread.edit()

    assert [c.id for c in thread.workspaces[-1].criteria] == [SURFACE, PROTEOME]
    assert sorted(thread.graph.steps) == sorted([SURFACE, STAGE, ROOT])


def _stating_a_criterion_no_step_answers(found: OperationalSpec) -> OperationalSpec:
    found.criteria.append(Criterion(id="c_unbound", text="something unbound"))
    return found


async def test_an_account_that_adds_what_the_edit_does_not_build_is_refused_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    entry = thread.spec.model_copy(deep=True)
    thread.frames(_stating_a_criterion_no_step_answers, declared=kept(SURFACE, STAGE))

    refusal = await thread.edit()

    assert isinstance(refusal, str), refusal
    assert "c_unbound" in refusal
    assert "drop_criterion" in refusal
    assert thread.committed == []
    assert thread.spec == entry
