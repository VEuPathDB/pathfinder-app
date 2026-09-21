"""A resumed turn's baseline, and what a push owes an earlier pass's pending change."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AttachNewRoot,
)
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    CANVAS,
    CANVAS_ROOT,
    PROTEOME,
    PROTEOME_PARAM,
    canvas_step,
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


def canvas_add(graph: StrategyGraph, *, under: str) -> None:
    """Join a new step to the root the way the graph editor commits it."""
    apply_operation(graph, AddLeafOp(step=canvas_step(), attach=AttachNewRoot()))
    join = StrategyStepNode(
        id=CANVAS_ROOT, search_name=COMBINE_SEARCH_NAME, operator=CombineOp.INTERSECT
    )
    apply_operation(graph, AddCombineOp(step=join, left_id=under, right_id=CANVAS))


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


async def test_a_resumed_baseline_takes_the_canvas_step_and_not_the_turns_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))
    await thread.edit()
    own_root = thread.graph.primary_root_id()
    assert own_root is not None
    canvas_add(thread.graph, under=own_root)

    await thread.next_turn(resumes_parked_call=True)

    assert [c.id for c in thread.before_turn.criteria] == [SURFACE, STAGE, CANVAS]
    assert sorted(c.id for c in thread.spec.criteria) == sorted(
        [SURFACE, STAGE, PROTEOME, CANVAS]
    )
    assert thread.ledger_diff().added_count == 1


async def test_a_turn_resumed_after_its_own_delete_still_reports_the_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    await thread.delete(STAGE)
    assert thread.ledger_diff().dropped_count == 1

    await thread.next_turn(resumes_parked_call=True)

    assert [c.id for c in thread.before_turn.criteria] == [SURFACE, STAGE]
    assert thread.criteria == [SURFACE]
    assert thread.ledger_diff().dropped_count == 1


def _moving_the_percentile_and_asking(found: OperationalSpec) -> OperationalSpec:
    return with_the_proteome(None)(with_the_percentile(90)(found))


async def test_a_pending_value_a_pass_calls_kept_is_pushed_and_the_delta_says_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The delta is computed against the answer, whatever the pass declared."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _moving_the_percentile_and_asking,
        declared=[*kept(SURFACE), *declared("changed", STAGE)],
        disposition="needs_user",
    )
    await thread.edit()
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, PROTEOME))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert committed_facts(thread.committed)[0] == OpFacts(
        kind="updateStepParams", step_id=STAGE, parameters={STAGE_PERCENTILE: "90"}
    )
    assert (delta.diff.changed_count, delta.diff.added_count) == (1, 1)
    assert STAGE not in delta.preserved_step_ids


def _dropping_the_stage_and_asking(found: OperationalSpec) -> OperationalSpec:
    found = with_the_proteome(None)(found)
    found.criteria = [c for c in found.criteria if c.id != STAGE]
    found.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(PROTEOME))
    )
    return found


def _restating_the_stage_and_dropping_the_question(
    found: OperationalSpec,
) -> OperationalSpec:
    held = stage_step()
    found.criteria = [c for c in found.criteria if c.id != PROTEOME]
    found.criteria.append(
        Criterion(
            id=STAGE,
            text="expressed in merozoites",
            search_name=held.search_name,
            resolved_params=dict(held.parameters),
        )
    )
    found.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(STAGE))
    )
    return found


async def test_a_pending_drop_taken_back_pushes_nothing_and_the_plan_is_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        _restating_the_stage_and_dropping_the_question,
        declared=[*kept(SURFACE, STAGE), *declared("dropped", PROTEOME)],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert thread.committed == []
    assert sorted(thread.graph.steps) == sorted([SURFACE, STAGE, ROOT])
    assert sorted(thread.criteria) == sorted([SURFACE, STAGE])
    assert thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] == NumberValue(
        value=40
    )


async def test_a_pending_drop_carried_through_a_second_question_is_still_owed_an_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _dropping_the_stage_and_asking,
        declared=declared("dropped", STAGE),
        disposition="needs_user",
    )
    await thread.edit()
    await thread.next_turn()
    thread.frames(with_the_proteome(None), declared=[], disposition="needs_user")
    await thread.edit()
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, PROTEOME))

    refusal = await thread.edit()

    assert isinstance(refusal, str), refusal
    assert STAGE in refusal
    assert thread.committed == []
    assert sorted(thread.graph.steps) == sorted([SURFACE, STAGE, ROOT])
    assert thread.spec.criteria[-1].resolved_params == {}
    assert PROTEOME_PARAM not in thread.spec.criteria[-1].resolved_params


def _an_option_on_the_stage(value: float, *, carrier: float | None = None) -> Draft:
    """An option stating the timepoint, beside a carrier this pass may re-bind."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        held = stage_step()
        if carrier is not None:
            for criterion in found.criteria:
                if criterion.id == STAGE:
                    criterion.resolved_params = {
                        **criterion.resolved_params,
                        STAGE_TIMEPOINT: NumberValue(value=carrier),
                    }
        found.criteria.append(
            Criterion(
                id="c_timepoint",
                text="at that hour",
                search_name=held.search_name,
                resolved_params={STAGE_TIMEPOINT: NumberValue(value=value)},
            )
        )
        return found

    return _draft


async def test_an_option_stating_the_value_the_strategy_holds_pushes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(_an_option_on_the_stage(40), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert thread.committed == []
    assert delta.diff.touched_count() == 0


async def test_an_option_against_a_value_this_pass_bound_on_the_carrier_leaves_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The value the pass bound on the criterion itself stands, and is what is pushed."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _an_option_on_the_stage(36, carrier=48),
        declared=[*kept(SURFACE), *declared("changed", STAGE)],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert committed_facts(thread.committed) == [
        OpFacts(
            kind="updateStepParams",
            step_id=STAGE,
            parameters={STAGE_TIMEPOINT: "48"},
        )
    ]


async def test_a_pending_drop_a_pass_calls_kept_is_not_pushed_as_a_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pass that says kept and leaves the criterion out has not let the drop stand."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _dropping_the_stage_and_asking,
        declared=declared("dropped", STAGE),
        disposition="needs_user",
    )
    await thread.edit()
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, PROTEOME, STAGE))

    refusal = await thread.edit()

    assert isinstance(refusal, str), committed_facts(thread.committed)
    assert thread.committed == []
    assert sorted(thread.graph.steps) == sorted([SURFACE, STAGE, ROOT])
