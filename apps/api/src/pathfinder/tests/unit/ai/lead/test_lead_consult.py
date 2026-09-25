"""The consult_user deferred tool: a blocking gate that asks the user design
questions at a genuine fork, then hands the answers back to the Lead so it can
re-run frame_problem with them. pydantic-ai paused on the first call, the user
answered in the carousel, the next POST carried the approval + a
data-user-question-answers payload, the backend extracted it into
state.user_question_answers, and the body now reads it.
"""

from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import (
    ConsultQuestion,
    PendingApproval,
    UserQuestionAnswer,
)
from pydantic_ai import RunContext, Tool
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintSource
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.tool_returns import returned, summary_text
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)


def _ctx(state: PipelineState) -> RunContext[LeadDeps]:
    return run_context_for(lead_deps(state), "call_1")


def _state() -> PipelineState:
    return pipeline_state()


def _answers(result: ToolReturn[list[UserQuestionAnswer]]) -> list[UserQuestionAnswer]:
    return returned(result, list[UserQuestionAnswer])


_QUESTIONS = [
    ConsultQuestion(id="q1", prompt="Fold-change threshold?"),
    ConsultQuestion(id="q2", prompt="Include microarray arm?"),
]


@pytest.mark.asyncio
async def test_returns_user_answers_and_instructs_replan() -> None:
    state = _state()
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_1", tool_name="consult_user"
    )
    state.user_question_answers = {
        "call_1": [
            UserQuestionAnswer(
                question_id="q1",
                prompt="Fold-change threshold?",
                chosen_labels=["2-fold"],
            ),
            UserQuestionAnswer(
                question_id="q2",
                prompt="Include microarray arm?",
                chosen_labels=["No"],
                note="RNA-seq is enough",
            ),
        ],
    }
    result = await consult_user(
        _ctx(state),
        questions=_QUESTIONS,
        reply="I will make this change and report what it takes with it.",
    )

    assert [a.question_id for a in _answers(result)] == ["q1", "q2"]
    assert summary_text(result) == (
        'The user answered your questions: "Fold-change threshold?" -> 2-fold; '
        '"Include microarray arm?" -> No - note: RNA-seq is enough. '
        "Now run frame_problem honoring these as hard constraints."
    )


@pytest.mark.asyncio
async def test_no_answers_yet_reports_awaiting() -> None:
    state = _state()
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_1", tool_name="consult_user"
    )
    result = await consult_user(
        _ctx(state),
        questions=_QUESTIONS,
        reply="I will make this change and report what it takes with it.",
    )
    assert _answers(result) == []
    assert summary_text(result) == (
        "Presented 2 question(s); awaiting the user's answers."
    )


def _answered(state: PipelineState, *answers: UserQuestionAnswer) -> None:
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_1", tool_name="consult_user"
    )
    state.user_question_answers = {"call_1": list(answers)}


class TestAnswersBecomeRequirements:
    """An answer is a requirement of the investigation, not prose in a log."""

    @pytest.mark.asyncio
    async def test_a_stated_combination_lands_as_a_combination_requirement(
        self,
    ) -> None:
        state = _state()
        _answered(
            state,
            UserQuestionAnswer(
                question_id="q1",
                prompt="How should the two evidence lines combine?",
                chosen_labels=["mass spectrometry evidence OR DeRisi expression"],
            ),
        )

        await consult_user(
            _ctx(state),
            questions=_QUESTIONS,
            reply="I will make this change and report what it takes with it.",
        )

        [requirement] = state.domain.requirements
        assert requirement.kind is ConstraintKind.COMBINATION
        assert (
            requirement.requested_value
            == "mass spectrometry evidence OR DeRisi expression"
        )
        assert requirement.label == "How should the two evidence lines combine?"
        assert requirement.source is ConstraintSource.USER_EXPLICIT
        assert requirement.hard is True

    @pytest.mark.asyncio
    async def test_a_combination_stated_in_the_note_is_read(self) -> None:
        state = _state()
        _answered(
            state,
            UserQuestionAnswer(
                question_id="q1",
                prompt="Anything else?",
                note="mass spec OR DeRisi expression",
            ),
        )

        await consult_user(
            _ctx(state),
            questions=_QUESTIONS,
            reply="I will make this change and report what it takes with it.",
        )

        [requirement] = state.domain.requirements
        assert requirement.kind is ConstraintKind.COMBINATION
        assert requirement.requested_value == "mass spec OR DeRisi expression"

    @pytest.mark.asyncio
    async def test_any_other_answer_lands_as_an_other_requirement(self) -> None:
        state = _state()
        _answered(
            state,
            UserQuestionAnswer(
                question_id="q1",
                prompt="Fold-change threshold?",
                chosen_labels=["2-fold", "log2 scale"],
            ),
        )

        await consult_user(
            _ctx(state),
            questions=_QUESTIONS,
            reply="I will make this change and report what it takes with it.",
        )

        [requirement] = state.domain.requirements
        assert requirement.kind is ConstraintKind.OTHER
        assert requirement.requested_value == "2-fold; log2 scale"

    @pytest.mark.asyncio
    async def test_an_empty_answer_states_no_requirement(self) -> None:
        state = _state()
        _answered(
            state,
            UserQuestionAnswer(question_id="q1", prompt="Fold-change threshold?"),
        )

        await consult_user(
            _ctx(state),
            questions=_QUESTIONS,
            reply="I will make this change and report what it takes with it.",
        )

        assert state.domain.requirements == []

    @pytest.mark.asyncio
    async def test_an_unlabelled_question_names_its_requirement_by_the_answer(
        self,
    ) -> None:
        state = _state()
        _answered(
            state,
            UserQuestionAnswer(question_id="q1", prompt="", chosen_labels=["2-fold"]),
        )

        await consult_user(
            _ctx(state),
            questions=_QUESTIONS,
            reply="I will make this change and report what it takes with it.",
        )

        [requirement] = state.domain.requirements
        assert requirement.label == "2-fold"

    @pytest.mark.asyncio
    async def test_the_same_answer_read_twice_is_one_requirement(self) -> None:
        state = _state()
        _answered(
            state,
            UserQuestionAnswer(
                question_id="q1",
                prompt="How should the two evidence lines combine?",
                chosen_labels=["mass spectrometry evidence OR DeRisi expression"],
            ),
        )

        await consult_user(
            _ctx(state),
            questions=_QUESTIONS,
            reply="I will make this change and report what it takes with it.",
        )
        await consult_user(
            _ctx(state),
            questions=_QUESTIONS,
            reply="I will make this change and report what it takes with it.",
        )

        assert len(state.domain.requirements) == 1


def test_the_call_takes_questions_and_the_reply_and_says_where_context_goes() -> None:
    """Background belongs to a question, so the schema has no top-level context."""
    tool = Tool(consult_user)
    schema = tool.function_schema.json_schema
    assert sorted(schema["properties"]) == ["questions", "reply"]
    assert schema["required"] == ["questions", "reply"]
    assert schema["additionalProperties"] is False
    assert tool.description is not None
    assert "question's ``context``" in tool.description


@pytest.mark.asyncio
async def test_answers_over_a_strategy_with_steps_route_to_the_edit() -> None:
    """A strategy that holds a step is changed by an edit, never framed again."""
    state = _state()
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_1", tool_name="consult_user"
    )
    state.user_question_answers = {
        "call_1": [
            UserQuestionAnswer(
                question_id="q1",
                prompt="Fold-change threshold?",
                chosen_labels=["2-fold"],
            ),
        ],
    }
    ctx = run_context_for(
        lead_deps(state, strategy_session=session_with_one_step()), "call_1"
    )

    result = await consult_user(
        ctx,
        questions=_QUESTIONS,
        reply="I will make this change and report what it takes with it.",
    )

    assert summary_text(result) == (
        'The user answered your questions: "Fold-change threshold?" -> 2-fold. '
        "Now run edit_strategy honoring these as hard constraints."
    )
