"""The consult answer round-trip: the frontend attaches a
``data-user-question-answers`` part (camelCase keys, as the carousel posts
it) to the assistant message; the backend must extract it into
``state.user_question_answers`` keyed by tool_call_id so the consult_user
body can read the user's answers on resume.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic_ai.ui.vercel_ai.request_types import DataUIPart, UIMessage

from pathfinder.ai.conversation._turn_helpers import (
    _extract_user_question_answers,
)
from pathfinder.ai.conversation.request_body import ChatRequestBody


def _body_with_answers() -> ChatRequestBody:
    part = DataUIPart(
        type="data-user-question-answers",
        data={
            "toolCallId": "call_42",
            "answers": [
                {
                    "questionId": "q1",
                    "prompt": "Fold-change threshold?",
                    "chosenLabels": ["2-fold"],
                    "note": "keep it lenient",
                },
                {
                    "questionId": "q2",
                    "prompt": "Include microarray arm?",
                    "chosenLabels": ["No"],
                    "note": "",
                },
            ],
        },
    )
    return ChatRequestBody(
        conversation_id=uuid4(),
        messages=[UIMessage(id="m1", role="assistant", parts=[part])],
    )


def test_extracts_camelcase_answers_keyed_by_tool_call_id() -> None:
    out = _extract_user_question_answers(_body_with_answers())
    assert set(out) == {"call_42"}
    answers = out["call_42"]
    assert [a.question_id for a in answers] == ["q1", "q2"]
    assert answers[0].chosen_labels == ["2-fold"]
    assert answers[0].note == "keep it lenient"
    assert answers[1].chosen_labels == ["No"]


def test_no_answers_part_yields_empty() -> None:
    body = ChatRequestBody(
        conversation_id=uuid4(),
        messages=[
            UIMessage(id="m1", role="assistant", parts=[]),
        ],
    )
    assert _extract_user_question_answers(body) == {}
