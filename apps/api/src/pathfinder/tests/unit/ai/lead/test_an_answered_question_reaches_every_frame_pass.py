"""An answered question reaches the FRAME pass that resolves it.

The answer comes typed or on a consult card, and a pass that stops on its
budget is retried with the same question and answer.
"""

from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import (
    ConsultQuestion,
    PendingApproval,
    UserQuestionAnswer,
)

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.graph.turn_records import AnsweredQuestions
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import PhaseRun
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._answered_draft import (
    ANSWER,
    QUESTION,
    answering_deps,
    classify,
    draft_deps,
    framed,
)

_CARD_ANSWER = '"Which localisation evidence?" -> signal peptide'


async def _answered_on_a_card() -> LeadDeps:
    """One turn: a new request, FRAME asks, the researcher answers the card."""
    deps = draft_deps("find surface proteins", domain=StrategyDomainState())
    classify(deps, IntentClassification.NEW_STRATEGY)
    deps.state.domain.operational_spec = framed(None)
    deps.state.domain.record_questions([QUESTION])
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_consult", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_consult": [
            UserQuestionAnswer(
                question_id="q1",
                prompt="Which localisation evidence?",
                chosen_labels=["signal peptide"],
            ),
        ],
    }
    await consult_user(
        run_context_for(deps, "call_consult"),
        questions=[ConsultQuestion(id="q1", prompt="Which localisation evidence?")],
    )
    return deps


async def test_a_card_answer_closes_the_questions_frame_asked() -> None:
    deps = await _answered_on_a_card()

    assert deps.state.domain.open_questions == []
    assert deps.state.turn_markers.answered == AnsweredQuestions(
        questions=[QUESTION], answer=_CARD_ANSWER, on_card=True
    )


async def test_the_frame_after_a_card_answer_reads_the_question_and_answer() -> None:
    deps = await _answered_on_a_card()

    order = frame_work_order("bind the evidence the user chose", deps)

    assert order.startswith(
        "FRAME work order: the previous pass ended with a question the "
        "researcher has now answered."
    )
    assert f"Question asked: {QUESTION.question}\nAnswer: {_CARD_ANSWER}\n" in order
    assert "an earlier turn bound the criteria" not in order


async def test_a_card_answer_with_no_open_question_changes_no_answer() -> None:
    deps = answering_deps()
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_consult", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_consult": [
            UserQuestionAnswer(question_id="q1", prompt="Arm?", chosen_labels=["No"]),
        ],
    }

    await consult_user(
        run_context_for(deps, "call_consult"),
        questions=[ConsultQuestion(id="q1", prompt="Arm?")],
    )

    assert deps.state.turn_markers.answered == AnsweredQuestions(
        questions=[QUESTION], answer=ANSWER
    )


@pytest.fixture
def stopping_dispatches(monkeypatch: pytest.MonkeyPatch) -> list[PhaseRun]:
    """Every dispatch binds one more criterion and stops on its budget."""
    runs: list[PhaseRun] = []

    async def _stub(
        *, run: PhaseRun, agent_deps: AgentDeps, deps: LeadDeps, **kwargs: object
    ) -> None:
        del kwargs
        runs.append(run)
        draft = agent_deps.agent_state.operational_spec_draft
        index = len(draft.criteria)
        draft.criteria.append(
            Criterion(id=f"c_extra{index}", text="extra", search_name="GenesByText"),
        )
        deps.last_phase_stop = PhaseStop(
            role="frame",
            reason=PhaseStopReason.BUDGET,
            tool_calls=60,
            criteria_bound=index + 1,
            criteria_declared=run.declared_criteria,
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stub)
    return runs


async def test_a_budget_retry_of_an_answer_repeats_the_answered_order(
    stopping_dispatches: list[PhaseRun],
) -> None:
    deps = answering_deps()

    await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("proceed", deps),
    )

    assert len(stopping_dispatches) == 2
    first, retry = (run.work_order for run in stopping_dispatches)
    assert retry == first
    assert f"Question asked: {QUESTION.question}\nAnswer: {ANSWER}\n" in retry
    assert "The Lead's brief: proceed" in retry
