"""A FRAME pass that follows an answered question continues the draft it finds.

The bound criteria are listed as done, so the pass spends its calls on the
criterion the answer concerns and leaves the others as they are.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.graph.turn_records import AnsweredQuestions
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_messages import budget_stop_work_order
from pathfinder.ai.lead.frame_dispatch import frame_work_order
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests.unit.ai.lead._answered_draft import (
    ANSWER,
    BOUND,
    OPEN,
    OPEN_PARAM,
    QUESTION,
    answering_deps,
    classify,
    draft_deps,
    framed,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import spec_facts
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    built_spec,
    built_tree,
    declared,
    kept,
    session_holding,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_ASKED_THIS_TURN = OpenQuestion(question="Which life-cycle stage decides c_stage?")
_FRESH = "Operationalize into criteria"


def test_classifying_the_answer_keeps_the_questions_it_answers() -> None:
    state = answering_deps().state

    assert state.domain.open_questions == []
    assert state.turn_markers.answered == AnsweredQuestions(
        questions=[QUESTION], answer=ANSWER
    )


def test_a_second_classification_keeps_a_question_asked_this_turn_open() -> None:
    deps = draft_deps("find surface proteins", domain=StrategyDomainState())
    classify(deps, IntentClassification.NEW_STRATEGY, call_id="c1")
    deps.state.domain.operational_spec = framed(None)
    deps.state.domain.record_questions([_ASKED_THIS_TURN])

    classify(deps, IntentClassification.EXTEND_STRATEGY, call_id="c2")

    assert deps.state.domain.open_questions == [_ASKED_THIS_TURN]
    assert deps.state.turn_markers.answered is None


def test_the_order_after_an_answer_lists_the_bound_criteria_and_the_answer() -> None:
    order = frame_work_order("proceed with signal-peptide evidence", answering_deps())

    assert order.startswith(
        "FRAME work order: the previous pass ended with a question the "
        "researcher has now answered. Continue it; this is not a fresh frame."
    )
    assert (
        "4 criteria are bound already. Do NOT call search_for_searches or "
        "set_criterion for any of them unless the answer below names it:"
    ) in order
    for criterion_id in BOUND:
        assert f"- [{criterion_id}] {criterion_id} property -> " in order
    assert (
        "These criteria hold open parameters the answer may decide:\n"
        f"- [{OPEN}] localised to the surface -> GenesBySignalPeptide "
        f"(open: {OPEN_PARAM})"
    ) in order
    assert f"Question asked: {QUESTION.question}\nAnswer: {ANSWER}\n" in order
    assert "The Lead's brief: proceed with signal-peptide evidence" in order
    assert _FRESH not in order


def test_a_fresh_thread_gets_the_fresh_order() -> None:
    deps = lead_deps(pipeline_state(user_prompt="find surface proteins"))

    order = frame_work_order("operationalize the goal", deps)

    assert order.startswith("FRAME work order: operationalize the goal")
    assert _FRESH in order


def test_a_strategy_on_the_site_is_not_briefed_as_a_continuation() -> None:
    """A draft hydrated from a live strategy has steps and no build outcome."""
    deps = draft_deps(ANSWER, strategy_session=session_with_one_step())
    classify(deps)

    order = frame_work_order("re-frame", deps)

    assert "no strategy is built from them yet" not in order
    assert _FRESH in order


async def test_a_draft_framed_after_a_clear_is_continued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clear, frame afresh and ask; the next message answers that draft."""
    thread = DisagreementThread(
        monkeypatch, spec=built_spec(), session=session_holding(built_tree())
    )
    thread.deps.state.user_message_id = uuid4()
    classify(thread.deps, IntentClassification.NEW_STRATEGY)
    await thread.clear()
    thread.frames(
        lambda _found: framed(None),
        declared=[],
        disposition="needs_user",
        asks=[QUESTION],
    )
    asked = await thread.frame()
    assert isinstance(asked, FrameResult)
    await thread.next_turn()
    thread.deps.state.user_prompt = ANSWER
    thread.deps.state.user_message_id = uuid4()
    classify(thread.deps)

    order = frame_work_order("proceed", thread.deps)

    assert order.splitlines()[0] == (
        "FRAME work order: the previous pass ended with a question the "
        "researcher has now answered. Continue it; this is not a fresh frame."
    )
    assert f"Question asked: {QUESTION.question}\nAnswer: {ANSWER}\n" in order
    assert all(f"- [{cid}] {cid} property -> " in order for cid in BOUND)


def test_a_new_request_over_an_unbuilt_draft_is_framed_afresh() -> None:
    message = "Forget that. Find transporters on chromosome 5."
    deps = draft_deps(message)
    classify(deps, IntentClassification.NEW_STRATEGY)

    order = frame_work_order("frame the new request", deps)

    assert order.startswith("FRAME work order: frame the new request\n")
    assert _FRESH in order
    assert "has now answered" not in order
    assert "Every other bound criterion stays exactly as it is" not in order


def test_a_bound_draft_with_no_question_is_continued_from_the_message() -> None:
    deps = draft_deps(
        "continue", domain=StrategyDomainState(operational_spec=framed(None))
    )
    classify(deps)

    order = frame_work_order("continue the frame", deps)

    assert order.startswith(
        "FRAME work order: an earlier turn bound the criteria below and no "
        "strategy is built from them yet."
    )
    assert "The user's message: continue" in order
    assert "Question asked" not in order


def test_the_order_after_a_budget_stop_keeps_its_words() -> None:
    order = budget_stop_work_order(framed(None), "find surface proteins")

    assert order.startswith(
        "FRAME work order: the previous pass ran out of its tool budget. "
        "Continue it; this is not a fresh frame."
    )
    assert (
        "5 criteria are bound already and stay exactly as they are. "
        "Do NOT call set_criterion for any of them:"
    ) in order
    assert "Question asked" not in order


async def test_the_answering_turn_binds_only_the_open_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FRAME asks, the researcher answers, the next pass resolves one criterion."""
    thread = DisagreementThread(
        monkeypatch,
        spec=OperationalSpec(goal="surface vaccine candidates"),
        session=session_holding(),
    )
    thread.frames(
        lambda _found: framed(None),
        declared=[],
        disposition="needs_user",
        asks=[QUESTION],
    )
    asked = await thread.frame()
    assert isinstance(asked, FrameResult)
    assert asked.disposition == "needs_user"
    await thread.next_turn()
    thread.deps.state.user_prompt = ANSWER
    thread.deps.state.user_message_id = uuid4()
    classify(thread.deps)
    thread.frames(
        lambda _found: framed("signal peptide"),
        declared=[*kept(*BOUND), *declared("changed", OPEN)],
    )

    answered = await thread.frame()

    assert isinstance(answered, FrameResult)
    order = thread.work_orders[-1]
    assert "the previous pass ended with a question" in order
    assert f"Question asked: {QUESTION.question}" in order
    assert f"Answer: {ANSWER}" in order
    assert all(f"- [{cid}] " in order for cid in BOUND)
    assert [c.id for c in thread.workspaces[-1].criteria if c.bound] == [
        *BOUND,
        OPEN,
    ]
    assert spec_facts(thread.spec) == {
        **{cid: {"value": cid} for cid in BOUND},
        OPEN: {OPEN_PARAM: "signal peptide"},
    }
