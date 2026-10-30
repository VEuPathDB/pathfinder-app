"""The calls every Lead arc shares: the classification it opens with and the
answer it ends on."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Literal

from assistant_core.models.scripted import scripted_call, terminal_call
from pydantic_ai.messages import ToolCallPart

from pathfinder.domain.reply_note import written_numbers

LeadTurnState = Literal["await_user", "complete"]

CLASSIFY = "classify_user_intent"
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def lead_final(
    prose: str,
    next_state: LeadTurnState,
    *,
    questions: Sequence[str] = (),
) -> ToolCallPart:
    """The Lead's final answer, as the turn contract reads it: what the arc
    wrote and any question it asks."""
    asked = [{"question": question} for question in questions]
    return terminal_call(
        {
            "prose": prose,
            "nextState": next_state,
            **({"askedQuestions": asked} if asked else {}),
        },
    )


def stated(kind: str, label: str, value: str) -> dict[str, Any]:
    """A requirement the researcher wrote, as a classification states it."""
    return {
        "kind": kind,
        "label": label,
        "requestedValue": value,
        "source": "user_explicit",
        "hard": True,
    }


def classify(classification: str, *requirements: dict[str, Any]) -> ToolCallPart:
    return scripted_call(
        CLASSIFY,
        {
            "intent": {
                "classification": classification,
                "inferredGoal": f"[mock] {classification}",
                **({"explicitConstraints": list(requirements)} if requirements else {}),
            },
        },
    )


def narrated(text: str) -> str:
    """The sentences of ``text`` that write no number, which only the facts
    beside a note state."""
    sentences = _SENTENCE_END.split(text.strip())
    return " ".join(s for s in sentences if s and not written_numbers(s))


def spoken(text: str) -> str:
    """``text`` with each number taken out."""
    for number in written_numbers(text):
        text = re.sub(rf"(?<![\w.,]){re.escape(number)}(?![\w%]|[.,]\d)", "", text)
    return " ".join(text.split())
