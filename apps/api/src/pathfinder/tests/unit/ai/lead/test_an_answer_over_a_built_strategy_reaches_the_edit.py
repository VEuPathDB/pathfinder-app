"""An answer to a question asked over a built strategy is carried by the edit."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.edit_messages import edit_work_order
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import Criterion, SpecStructure
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.tests.unit.ai.lead._answered_draft import ANSWER, QUESTION, classify
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    STAGE,
    SURFACE,
    DisagreementThread,
    built_spec,
    built_tree,
    joined,
    kept,
    leaf,
    session_holding,
)

_ANSWERED = f"Question asked: {QUESTION.question}\nAnswer: {ANSWER}"


def _answering(
    monkeypatch: pytest.MonkeyPatch, kind: IntentClassification
) -> DisagreementThread:
    """A built thread holding one open question, and the message that follows."""
    thread = DisagreementThread(
        monkeypatch, spec=built_spec(), session=session_holding(built_tree())
    )
    state = thread.deps.state
    state.domain.open_questions = [QUESTION]
    state.user_prompt = ANSWER
    state.user_message_id = uuid4()
    classify(thread.deps, kind)
    return thread


@pytest.mark.parametrize(
    "kind",
    [
        IntentClassification.CLARIFICATION_RESPONSE,
        IntentClassification.NEW_STRATEGY,
        IntentClassification.EDIT_STRATEGY,
    ],
)
def test_frame_is_not_offered_over_a_built_strategy(
    monkeypatch: pytest.MonkeyPatch, kind: IntentClassification
) -> None:
    thread = _answering(monkeypatch, kind)

    offered = tools_the_turn_offers(thread.deps, ["frame_problem", "edit_strategy"])

    assert offered == frozenset({"edit_strategy"})


async def test_the_edit_order_carries_the_question_and_its_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _answering(monkeypatch, IntentClassification.CLARIFICATION_RESPONSE)
    thread.frames(lambda found: found, declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    order = thread.work_orders[-1]
    assert order.splitlines()[:5] == [
        "EDIT work order: change the strategy",
        f"The user's message: {ANSWER}",
        "The message answers what the previous pass asked:",
        f"Question asked: {QUESTION.question}",
        f"Answer: {ANSWER}",
    ]


def _budget_stops(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Each FRAME pass binds one criterion and stops at its budget."""
    orders: list[str] = []

    async def _stopped(**kwargs: Any) -> None:
        orders.append(kwargs["run"].work_order)
        agent_deps: AgentDeps = kwargs["agent_deps"]
        deps: LeadDeps = kwargs["deps"]
        draft = agent_deps.agent_state.operational_spec_draft
        draft.criteria.append(
            Criterion(
                id=f"c_{len(draft.criteria)}", text="a signal peptide", search_name="S"
            )
        )
        deps.last_phase_stop = PhaseStop(
            role="frame",
            reason=PhaseStopReason.BUDGET,
            tool_calls=60,
            criteria_bound=len(draft.criteria),
            criteria_declared=2,
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stopped)
    return orders


async def test_the_budget_retry_of_the_edit_carries_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _answering(monkeypatch, IntentClassification.CLARIFICATION_RESPONSE)
    orders = _budget_stops(monkeypatch)

    await thread.edit()

    assert orders[1].splitlines()[:5] == [
        (
            "EDIT work order: the previous pass ran out of its tool budget; "
            "continue that edit"
        ),
        f"The user's message: {ANSWER}",
        "The message answers what the previous pass asked:",
        f"Question asked: {QUESTION.question}",
        f"Answer: {ANSWER}",
    ]


def _section(order: str, heading: str) -> list[str]:
    """The heading and the line under it, or nothing when the order lacks it."""
    lines = order.splitlines()
    return lines[lines.index(heading) :][:2] if heading in lines else []


async def test_the_budget_retry_of_the_edit_carries_the_pending_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry owes the unpushed changes a disposition, so it is shown them."""
    planned = built_spec()
    planned.criteria.append(
        Criterion(id="c_planned", text="no human ortholog", search_name="S")
    )
    planned.structure = SpecStructure(
        root=joined(
            CombineOp.INTERSECT,
            joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(STAGE)),
            leaf("c_planned"),
        )
    )
    thread = DisagreementThread(
        monkeypatch, spec=planned, session=session_holding(built_tree())
    )
    state = thread.deps.state
    state.domain.open_questions = [QUESTION]
    state.user_prompt = ANSWER
    state.user_message_id = uuid4()
    classify(thread.deps, IntentClassification.CLARIFICATION_RESPONSE)
    orders = _budget_stops(monkeypatch)

    await thread.edit()

    pending = [
        (
            "NOT PUSHED YET. An earlier pass of this thread stated these and the "
            "strategy does not hold them. State a disposition in `changes` for "
            "each of them too: repeat it to let it stand, or take it back by "
            "stating the criterion the strategy holds with set_criterion."
        ),
        "- [c_planned] no human ortholog has no step on the strategy yet.",
    ]
    assert [_section(order, pending[0]) for order in orders] == [pending, pending]
    assert [f"Answer: {ANSWER}" in order for order in orders] == [True, True]
    assert orders[1].splitlines()[0] == (
        "EDIT work order: the previous pass ran out of its tool budget; "
        "continue that edit"
    )


def test_an_edit_order_with_no_answer_names_no_question() -> None:
    spec = built_spec()
    order = edit_work_order(
        "swap the organism",
        "use P. vivax",
        spec,
        pending=SpecDiff(),
        answered=spec,
        answer=None,
    )

    assert order.splitlines()[:3] == [
        "EDIT work order: swap the organism",
        "The user's message: use P. vivax",
        "",
    ]
    assert _ANSWERED not in order
