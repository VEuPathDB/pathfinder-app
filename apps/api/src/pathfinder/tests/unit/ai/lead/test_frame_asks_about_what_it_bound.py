"""A FRAME pass that stops on the user asks about a criterion it recorded.

A pass that only reads a search's parameter sheet writes nothing into the
draft, so its questions reach no criterion and the answer has nowhere to land.
"""

from __future__ import annotations

import pytest

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    PROTEOME_PARAM,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import (
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
    kept,
    recorded,
    session_holding,
)

THRESHOLD = OpenQuestion(
    question="How many distinct peptides must a gene be detected by?",
    dimension=ConstraintKind.STATISTICAL_THRESHOLD,
    recommended_value="2",
)


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _pins_the_sheet() -> Draft:
    """The pass read the search's parameter sheet and recorded nothing."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        return found

    return _draft


def _asks_without_binding(thread: DisagreementThread) -> None:
    """Script the pass that ends on the user over an untouched draft."""
    thread.frames(
        _pins_the_sheet(),
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[THRESHOLD],
    )


def _binds_with_an_open_slot(thread: DisagreementThread) -> None:
    """Script the pass that records the criterion and then asks about it."""
    thread.frames(
        with_the_proteome(None),
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[THRESHOLD],
    )


async def test_a_pass_that_asks_without_binding_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The questions reach no criterion, so the pass is sent back to record one."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    _asks_without_binding(thread)

    refusal = await thread.edit()

    assert isinstance(refusal, str), refusal
    assert "set_criterion" in refusal
    assert THRESHOLD.question in refusal
    assert thread.criteria == [SURFACE, STAGE]
    assert thread.committed == []


async def test_a_pass_that_binds_before_it_asks_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A draft that holds the criterion with an open slot is the shape asked for."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    _binds_with_an_open_slot(thread)

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert delta.disposition == "needs_user"
    assert thread.committed == []
    assert _open_params(thread) == [PROTEOME_PARAM]


async def test_a_pass_that_binds_and_asks_about_nothing_open_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A draft with every value decided holds no slot the answer lands in."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        with_the_proteome(2),
        declared=kept(SURFACE, STAGE),
        disposition="needs_user",
        asks=[THRESHOLD],
    )

    refusal = await thread.edit()

    assert isinstance(refusal, str), refusal
    assert "open slot" in refusal
    assert thread.criteria == [SURFACE, STAGE]


async def test_the_pass_is_refused_once_a_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second pass that still asks about nothing reaches the Lead."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    _asks_without_binding(thread)
    assert isinstance(await thread.edit(), str)
    _asks_without_binding(thread)

    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert delta.disposition == "needs_user"
    assert [q.question for q in delta.open_questions] == [THRESHOLD.question]


async def test_the_retry_records_the_criterion_and_the_answer_builds_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refused turn ends with the criterion open, and the answer pushes it."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    _asks_without_binding(thread)
    assert isinstance(await thread.edit(), str)
    _binds_with_an_open_slot(thread)
    asked = await thread.edit()
    assert isinstance(asked, EditDelta), asked
    assert thread.criteria == [SURFACE, STAGE, PROTEOME]
    assert thread.committed == []

    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, PROTEOME))
    delta = await thread.edit()

    assert isinstance(delta, EditDelta), delta
    assert [(op.kind, op.step_id) for op in committed_facts(thread.committed)] == [
        ("addLeaf", PROTEOME),
        ("addCombine", _root_of(thread)),
    ]
    assert spec_facts(thread.spec) == {
        SURFACE: {},
        STAGE: {STAGE_PERCENTILE: "80", STAGE_TIMEPOINT: "40"},
        PROTEOME: {PROTEOME_PARAM: "2"},
    }
    assert delta.added_step_ids == [PROTEOME]


def _open_params(thread: DisagreementThread) -> list[str]:
    """Every parameter the committed spec leaves for the user, criterion order."""
    return [
        slot.param_name
        for criterion in thread.spec.criteria
        for slot in criterion.open_params
    ]


def _root_of(thread: DisagreementThread) -> str:
    root = thread.graph.primary_root_id()
    assert root is not None
    return root
