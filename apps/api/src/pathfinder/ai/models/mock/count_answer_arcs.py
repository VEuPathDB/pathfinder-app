"""Lead arcs that answer a count question from the counts the facts show: a
step's count, the result's, and the difference of the two."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic import Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.reads import ToolAnswer, last_return

_LIVE = "get_live_strategy_state"


class _Step(ToolAnswer):
    display_name: str = ""
    estimated_size: int | None = None
    is_root: bool = False


class _Live(ToolAnswer):
    root_count: int | None = None
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
    if live is None or leaf is None or live.root_count is None:
        return "The strategy read did not answer."
    size = leaf.estimated_size or 0
    return (
        f"The {leaf.display_name} step returns {size} genes and the result "
        f"{live.root_count}, so the other filters remove {size - live.root_count}."
    )


def derived_count(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read the strategy and answer with a step's count, the result's, and the
    difference of the two."""
    return [
        classify("follow_up_question"),
        scripted_call(_LIVE, {}),
        lead_final(_answer(last_return(messages, _LIVE, _Live)), "complete"),
    ]


__all__ = ["derived_count"]
