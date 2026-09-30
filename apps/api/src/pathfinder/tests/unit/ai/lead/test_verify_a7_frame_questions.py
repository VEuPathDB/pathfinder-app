"""Attacks on the refusal of a needs_user pass whose questions bind to nothing.

Each test states a case the release verifier constructed; the assertions pin
what the dispatch does with it today.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.tests._support.bound_values import stated
from pathfinder.tests.unit.ai.lead._disagreement_drafts import with_the_proteome
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_PERCENTILE,
    SURFACE,
    DisagreementThread,
    built_spec,
    built_tree,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)
from pathfinder.tests.unit.ai.lead.conftest import requirement

FORK = SlotQuestion(
    question="Two searches fit surface proteins: signal peptide or GPI anchor?",
    dimension=ConstraintKind.DATA_TYPE,
    recommended_value="GenesBySignalPeptide",
)
THRESHOLD = SlotQuestion(
    question="How many distinct peptides must a gene be detected by?",
    dimension=ConstraintKind.STATISTICAL_THRESHOLD,
    recommended_value="2",
)


def _built_thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _fresh_thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=OperationalSpec(goal="vaccine candidates"),
        session=session_holding(),
    )


def _binds_everything(found: OperationalSpec) -> OperationalSpec:
    spec = built_spec()
    spec.goal = found.goal
    return spec


def _unchanged(found: OperationalSpec) -> OperationalSpec:
    return found


def _asks_over_an_unchanged_draft(thread: DisagreementThread) -> None:
    thread.frames(
        _unchanged,
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[THRESHOLD],
    )


async def test_1a_a_fresh_frame_that_bound_everything_and_asks_a_fork(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case (a): a design fork with every value bound is refused once.

    The refusal asks for a null parameter and keeps the criteria the pass
    bound, so the retry does not bind them again.
    """
    thread = _fresh_thread(monkeypatch)
    thread.frames(_binds_everything, declared=[], disposition="needs_user", asks=[FORK])

    result = await thread.frame()

    assert isinstance(result, str), result
    assert "no criterion of the spec holds an open slot" in result
    assert "null for every parameter" in result
    spec = thread.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == [
        c.id for c in _binds_everything(OperationalSpec()).criteria
    ]


async def test_1a_second_pass_with_the_same_fork_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _fresh_thread(monkeypatch)
    thread.frames(_binds_everything, declared=[], disposition="needs_user", asks=[FORK])
    assert isinstance(await thread.frame(), str)
    thread.frames(_binds_everything, declared=[], disposition="needs_user", asks=[FORK])

    result = await thread.frame()

    assert isinstance(result, FrameResult), result
    assert result.disposition == "needs_user"
    assert [q.question for q in thread.deps.state.domain.open_questions] == [
        FORK.question
    ]


async def test_1b_a_budget_stop_that_asks_nothing_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case (b): the stopped pass is reported from the draft, never refused."""
    thread = _fresh_thread(monkeypatch)

    async def _stopped(*, deps: LeadDeps, **kwargs: object) -> None:
        del kwargs
        deps.last_phase_stop = PhaseStop(role="frame", reason=PhaseStopReason.BUDGET)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stopped)
    result = await thread.frame()

    assert isinstance(result, FrameResult), result
    assert result.disposition == "needs_user"
    assert result.open_questions == []
    assert "tool budget" in result.summary


def _moves_a_built_value(found: OperationalSpec) -> OperationalSpec:
    stage = next(c for c in found.criteria if c.id == STAGE)
    stage.resolved_params[STAGE_PERCENTILE] = stated(NumberValue(value=90))
    return found


async def test_1c_an_edit_that_moves_a_value_and_asks_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case (c): no open slot anywhere, the value moved, one question asked.

    The undeclared move is refused first, and the spec goes back as found.
    """
    thread = _built_thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _moves_a_built_value,
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[THRESHOLD],
    )

    result = await thread.edit()

    assert isinstance(result, str), result
    assert "the account of it does not match what happened" in result
    stage = next(c for c in thread.spec.criteria if c.id == STAGE)
    assert stage.param_values[STAGE_PERCENTILE] == NumberValue(value=80)


async def test_1d_the_latched_second_pass_records_questions_over_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case (d): after the latch the questions are recorded; the next turn
    reads the recommendation and refuses the same pass once again."""
    thread = _built_thread(monkeypatch)
    await thread.next_turn()
    _asks_over_an_unchanged_draft(thread)
    assert isinstance(await thread.edit(), str)
    _asks_over_an_unchanged_draft(thread)
    delta = await thread.edit()
    assert isinstance(delta, EditDelta)

    domain = thread.deps.state.domain
    assert [q.question for q in domain.open_questions] == [THRESHOLD.question]
    assert thread.criteria == [SURFACE, STAGE]

    await thread.next_turn()
    domain = thread.deps.state.domain
    domain.record_recommendations()
    assert [c.requested_value for c in domain.recommendations] == ["2"]
    assert domain.requirements == []
    assert thread.deps.unbound_questions_reported is False
    _asks_over_an_unchanged_draft(thread)
    third = await thread.edit()
    assert isinstance(third, str), third


def _drops_stage_and_binds_proteome_open(found: OperationalSpec) -> OperationalSpec:
    spec = with_the_proteome(None)(found)
    spec.criteria = [c for c in spec.criteria if c.id != STAGE]
    spec.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(SURFACE), leaf("c_proteome"))
    )
    return spec


def _dropped(*ids: str) -> list[CriterionChange]:
    return [
        CriterionChange(criterion_id=i, disposition="dropped", reason="gone")
        for i in ids
    ]


async def test_1e_a_drop_beside_an_open_slot_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _built_thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _drops_stage_and_binds_proteome_open,
        declared=[*kept(SURFACE), *_dropped(STAGE)],
        disposition="needs_user",
        asks=[THRESHOLD],
    )
    result = await thread.edit()
    assert isinstance(result, EditDelta), result
    assert result.disposition == "needs_user"
    assert [q.question for q in result.open_questions] == [THRESHOLD.question]
    assert thread.criteria == [SURFACE, "c_proteome"]


_STAGE_FLOOR = requirement(
    ConstraintKind.PERCENTILE, "expression", "top 10 percent in gametocytes"
)


def _drops_the_floor_the_researcher_stated(found: OperationalSpec) -> OperationalSpec:
    spec = _drops_stage_and_binds_proteome_open(found)
    spec.dropped.append(
        DroppedCriterion(
            text="top 10 percent in gametocytes",
            reason="no search ranks gametocyte expression",
            requirement=_STAGE_FLOOR,
        )
    )
    return spec


async def test_1f_an_edit_that_asks_offers_to_withdraw_what_no_search_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _built_thread(monkeypatch)
    thread.deps.state.domain.requirements = [_STAGE_FLOOR]
    await thread.next_turn()
    thread.frames(
        _drops_the_floor_the_researcher_stated,
        declared=[*kept(SURFACE), *_dropped(STAGE)],
        disposition="needs_user",
        asks=[THRESHOLD],
    )

    result = await thread.edit()

    assert isinstance(result, EditDelta), result
    assert [
        (q.question, [o.label for o in q.options]) for q in result.open_questions
    ] == [
        (THRESHOLD.question, []),
        (
            (
                "No search on this site states 'top 10 percent in gametocytes'. "
                "Drop it from the request?"
            ),
            [
                "Drop top 10 percent in gametocytes",
                "Keep top 10 percent in gametocytes",
            ],
        ),
    ]
    assert [q.prompt for q in result.card_questions] == [
        q.question for q in result.open_questions
    ]
