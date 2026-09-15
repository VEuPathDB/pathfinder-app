"""The read budgets one run may spend on the discovery and research tools."""

from __future__ import annotations

from pathfinder.ai.agents.tool_vocabulary import build_tool_repetition_guard


def _distinct_calls(tool: str, count: int) -> list[str | None]:
    guard = build_tool_repetition_guard()
    return [
        None if block is None else block.rule
        for block in (
            guard.check(tool, {"query": f"query {i}"}, tool_call_id=f"c{i}")
            for i in range(count)
        )
    ]


def test_twelve_distinct_literature_searches_fit_one_turn_and_the_thirteenth_does_not() -> (
    None
):
    assert _distinct_calls("research_literature_search", 13) == [None] * 12 + [
        "call_cap"
    ]


def test_twelve_distinct_web_searches_fit_one_turn_and_the_thirteenth_does_not() -> (
    None
):
    assert _distinct_calls("research_web_search", 13) == [None] * 12 + ["call_cap"]
