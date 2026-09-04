"""The consult_user deferred tool: a blocking gate that asks the user design
questions at a genuine fork, then hands the answers back to the Lead so it can
re-run frame_problem with them. pydantic-ai paused on the first call, the user
answered in the carousel, the next POST carried the approval + a
data-user-question-answers payload, the backend extracted it into
state.user_question_answers, and the body now reads it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import (
    ConsultQuestion,
    PendingApproval,
    UserQuestionAnswer,
)
from pydantic_ai import Tool

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintSource


def _ctx(state: PipelineState) -> Any:
    ctx = MagicMock()
    ctx.tool_call_id = "call_1"
    ctx.deps = MagicMock()
    ctx.deps.state = state
    return ctx


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
    )


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
    result = await consult_user(_ctx(state), questions=_QUESTIONS)

    assert [a.question_id for a in result.return_value] == ["q1", "q2"]
    assert "Fold-change threshold?" in result.content
    assert "2-fold" in result.content
    assert "RNA-seq is enough" in result.content
    # The Lead is told to re-frame with the answers, not to execute.
    assert "frame_problem" in result.content


@pytest.mark.asyncio
async def test_no_answers_yet_reports_awaiting() -> None:
    state = _state()
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_1", tool_name="consult_user"
    )
    result = await consult_user(_ctx(state), questions=_QUESTIONS)
    assert result.return_value == []
    assert "2" in result.content  # presented 2 questions
    assert "awaiting" in result.content.lower()


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

        await consult_user(_ctx(state), questions=_QUESTIONS)

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

        await consult_user(_ctx(state), questions=_QUESTIONS)

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

        await consult_user(_ctx(state), questions=_QUESTIONS)

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

        await consult_user(_ctx(state), questions=_QUESTIONS)

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

        await consult_user(_ctx(state), questions=_QUESTIONS)

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

        await consult_user(_ctx(state), questions=_QUESTIONS)
        await consult_user(_ctx(state), questions=_QUESTIONS)

        assert len(state.domain.requirements) == 1


def test_the_call_takes_only_questions_and_says_where_context_goes() -> None:
    """Background belongs to a question, so the schema has no top-level context."""
    tool = Tool(consult_user)
    schema = tool.function_schema.json_schema
    assert sorted(schema["properties"]) == ["questions"]
    assert schema["additionalProperties"] is False
    assert "question's ``context``" in tool.description
