"""The calls every Lead arc shares: the classification it opens with and the
answer it ends on."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from assistant_core.models.scripted import scripted_call, terminal_call
from pydantic_ai.messages import ToolCallPart

LeadTurnState = Literal["await_user", "complete"]

CLASSIFY = "classify_user_intent"


def lead_final(
    prose: str,
    next_state: LeadTurnState,
    *,
    strategy_changed: bool = False,
    sources: Sequence[Mapping[str, str]] = (),
    questions: Sequence[str] = (),
) -> ToolCallPart:
    """The Lead's final answer, as the turn contract reads it: what the arc
    wrote, the references it cites and any question it asks."""
    asked = [{"question": question} for question in questions]
    return terminal_call(
        {
            "prose": prose,
            "nextState": next_state,
            "strategyChanged": strategy_changed,
            "sources": [dict(source) for source in sources],
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
