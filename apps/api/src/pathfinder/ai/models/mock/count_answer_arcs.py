"""Lead arcs that answer a count question with references to the counts the
facts hold: a step's count, the result's, and the difference of the two."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic import Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.reads import ToolAnswer, last_return

_LIVE = "get_live_strategy_state"


class _Step(ToolAnswer):
    step_id: str
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
        f"The first search step returns [count:{leaf.step_id}] and the result "
        f"[root], so the other filters remove [diff:{leaf.step_id},root]."
    )


def derived_count(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read the strategy and answer with references to a step's count, the
    result's, and the difference of the two."""
    return [
        classify("follow_up_question"),
        scripted_call(_LIVE, {}),
        lead_final(_answer(last_return(messages, _LIVE, _Live)), "complete"),
    ]


__all__ = ["derived_count"]
