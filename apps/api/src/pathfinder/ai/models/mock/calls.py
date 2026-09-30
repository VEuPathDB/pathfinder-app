"""The calls every Lead arc shares: the classification it opens with and the
answer it ends on."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from assistant_core.models.scripted import scripted_call, terminal_call
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.lead.facts_in_prose import outside_the_facts

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
    """The sentences of ``text`` that print no number, identifier or link, which
    the facts part beside the reply shows instead."""
    sentences = _SENTENCE_END.split(text.strip())
    return " ".join(s for s in sentences if s and not outside_the_facts(s, "", ()))


def spoken(text: str) -> str:
    """``text`` with each number, identifier and link it prints taken out."""
    for printed in outside_the_facts(text, "", ()):
        text = re.sub(rf"(?<!\w){re.escape(printed)}(?!\w)", "", text)
    return " ".join(text.split())
