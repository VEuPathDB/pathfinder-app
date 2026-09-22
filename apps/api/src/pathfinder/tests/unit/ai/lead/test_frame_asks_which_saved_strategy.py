"""A pass that asks which saved strategy the user means records the choice.

A saved-strategy criterion has no parameter sheet, so the way forward the
refusal offers is the saved-strategy slot ``set_criterion`` writes when the
name it is given matches nothing.
"""

from __future__ import annotations

import pytest

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.tools.standalone._frame_saved import SAVED_STRATEGY_SLOT
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    kept,
    recorded,
    session_holding,
)

SAVED = "c_saved"
WHICH_ONE = OpenQuestion(
    question="Which saved strategy: 'kinase panel', 'surfaceome v2'?",
    dimension=ConstraintKind.OTHER,
    recommended_value="surfaceome v2",
)


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _read_the_listing_only() -> Draft:
    """The pass listed the saved strategies and recorded no criterion."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        return found

    return _draft


def _records_the_pending_choice() -> Draft:
    """What ``set_criterion`` writes when the name matches no saved strategy.

    The criterion is bound to nothing and carries the saved-strategy slot, so
    the answer has an address.
    """

    def _draft(found: OperationalSpec) -> OperationalSpec:
        after = found.model_copy(deep=True)
        after.criteria.append(
            Criterion(
                id=SAVED,
                text="start from the strategy the user saved",
                role="seed",
                open_params=[
                    OpenSlot(
                        criterion_id=SAVED,
                        param_name=SAVED_STRATEGY_SLOT,
                        question=WHICH_ONE.question,
                        options=["kinase panel", "surfaceome v2"],
                    )
                ],
            )
        )
        return after

    return _draft


async def test_a_pass_that_asks_before_it_records_the_choice_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The question reaches no criterion, so the pass is sent back to record it."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _read_the_listing_only(),
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[WHICH_ONE],
    )

    refusal = await thread.edit()

    assert isinstance(refusal, str), refusal
    assert WHICH_ONE.question in refusal
    assert thread.criteria == [SURFACE, STAGE]


async def test_the_refusal_names_a_way_a_saved_strategy_question_can_follow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A saved-strategy criterion has no sheet, so nulling a parameter is no path."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _read_the_listing_only(),
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[WHICH_ONE],
    )

    refusal = await thread.edit()

    assert isinstance(refusal, str), refusal
    assert "saved_strategy" in refusal
    assert "set_criterion" in refusal


async def test_a_pass_that_records_the_pending_choice_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unbound criterion carrying the saved-strategy slot is the shape asked for."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _records_the_pending_choice(),
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[WHICH_ONE],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert delta.disposition == "needs_user"
    assert thread.criteria == [SURFACE, STAGE, SAVED]
    assert thread.committed == []
    assert _open_slots(thread) == [SAVED_STRATEGY_SLOT]


async def test_the_retry_records_the_choice_the_first_pass_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refused turn still ends with the question and an address for it."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _read_the_listing_only(),
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[WHICH_ONE],
    )
    assert isinstance(await thread.edit(), str)
    thread.frames(
        _records_the_pending_choice(),
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[WHICH_ONE],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert [q.question for q in delta.open_questions] == [WHICH_ONE.question]
    assert thread.criteria == [SURFACE, STAGE, SAVED]
    assert _open_slots(thread) == [SAVED_STRATEGY_SLOT]


def _open_slots(thread: DisagreementThread) -> list[str]:
    """Every parameter the committed spec leaves for the user, criterion order."""
    return [
        slot.param_name
        for criterion in thread.spec.criteria
        for slot in criterion.open_params
    ]
