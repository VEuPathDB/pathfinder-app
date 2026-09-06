"""Turn helpers: site id resolution and the consult answer round-trip.

The frontend attaches a ``data-user-question-answers`` part (camelCase keys)
to the assistant message; the backend extracts it keyed by tool_call_id.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai.ui.vercel_ai.request_types import DataUIPart, UIMessage

from pathfinder.ai.conversation._turn_helpers import (
    _extract_user_question_answers,
    resolve_site_id,
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


def test_resolve_prefers_chat_site_id_over_body() -> None:
    assert (
        resolve_site_id(
            chat_site_id="plasmodb",
            body_site_id="toxodb",
            conversation_id=uuid4(),
        )
        == "plasmodb"
    )


def test_resolve_falls_back_to_body_when_chat_is_none() -> None:
    assert (
        resolve_site_id(
            chat_site_id=None,
            body_site_id="plasmodb",
            conversation_id=uuid4(),
        )
        == "plasmodb"
    )


def test_resolve_falls_back_to_body_when_chat_is_empty() -> None:
    assert (
        resolve_site_id(
            chat_site_id="",
            body_site_id="plasmodb",
            conversation_id=uuid4(),
        )
        == "plasmodb"
    )


def test_resolve_raises_when_both_are_empty() -> None:
    conversation_id = uuid4()
    with pytest.raises(ValueError, match=f"chat {conversation_id}"):
        resolve_site_id(
            chat_site_id="",
            body_site_id="",
            conversation_id=conversation_id,
        )


def test_resolve_raises_when_both_are_none_and_empty() -> None:
    with pytest.raises(ValueError, match="site_id could not be resolved"):
        resolve_site_id(
            chat_site_id=None,
            body_site_id="",
            conversation_id=uuid4(),
        )


def test_resolve_treats_whitespace_as_empty() -> None:
    with pytest.raises(ValueError, match="site_id could not be resolved"):
        resolve_site_id(
            chat_site_id="   ",
            body_site_id="\t",
            conversation_id=uuid4(),
        )
