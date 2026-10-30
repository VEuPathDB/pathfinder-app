"""Lead arcs that answer a count question with a note beside the counts the
facts show: a step's count, the result's, and what lies between them."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic import Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.reads import ToolAnswer, last_return

_LIVE = "get_live_strategy_state"


class _Step(ToolAnswer):
    step_id: str
    display_name: str = ""
    estimated_size: int | None = None
    is_root: bool = False


class _Live(ToolAnswer):
    steps: list[_Step] = Field(default_factory=list)


def _answer(live: _Live | None) -> str:
    leaf = next(
        (
            s
            for s in ([] if live is None else live.steps)
            if not s.is_root and s.estimated_size is not None
        ),
        None,
    )
    if leaf is None:
        return "The strategy read did not answer."
    return (
        f"The facts show the count of the first search step, {leaf.display_name}, "
        "beside the result's; the other filters remove the genes between the two."
    )


def derived_count(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read the strategy and answer with a note on a step's count and the
    result's, which the facts show."""
    return [
        classify("follow_up_question"),
        scripted_call(_LIVE, {}),
        lead_final(_answer(last_return(messages, _LIVE, _Live)), "complete"),
    ]


__all__ = ["derived_count"]
