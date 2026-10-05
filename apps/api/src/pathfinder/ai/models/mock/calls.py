"""The calls every Lead arc shares: the classification it opens with and the
answer it ends on."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from assistant_core.models.scripted import scripted_call, terminal_call
from pydantic_ai.messages import ToolCallPart

from pathfinder.domain.reply_references import shape_faults

LeadTurnState = Literal["await_user", "complete"]

CLASSIFY = "classify_user_intent"
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def lead_final(
    prose: str,
    next_state: LeadTurnState,
    *,
    strategy_changed: bool = False,
    questions: Sequence[str] = (),
) -> ToolCallPart:
    """The Lead's final answer, as the turn contract reads it: what the arc
    wrote and any question it asks."""
    asked = [{"question": question} for question in questions]
    return terminal_call(
        {
            "prose": prose,
            "nextState": next_state,
            "strategyChanged": strategy_changed,
            **({"askedQuestions": asked} if asked else {}),
        },
    )


def classify(classification: str) -> ToolCallPart:
    return scripted_call(
        CLASSIFY,
        {
            "intent": {
                "classification": classification,
                "inferredGoal": f"[mock] {classification}",
            },
        },
    )


def narrated(text: str) -> str:
    """The sentences of ``text`` that write no number, identifier or link, which
    a reply writes only as a reference."""
    sentences = _SENTENCE_END.split(text.strip())
    return " ".join(s for s in sentences if s and not shape_faults(s))


def spoken(text: str) -> str:
    """``text`` with each number, identifier and link taken out."""
    for fault in shape_faults(text):
        text = re.sub(rf"(?<!\w){re.escape(fault.token)}(?!\w)", "", text)
    return " ".join(text.split())
