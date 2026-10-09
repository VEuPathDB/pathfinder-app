"""A build pass of the mock FRAME reads the user's cases before it ranks a
search, as FRAME's procedure asks."""

from __future__ import annotations

from pathfinder.tests.unit.ai.models._mock_turns import args_of, names, play

_ORDER = "Frame work order: mock frame"


def test_a_build_pass_searches_cases_before_the_catalog() -> None:
    message = "Find secreted membrane genes. [[arc:intersect]]"

    calls = play("frame", "plasmodb", message, work_order=_ORDER)

    assert names(calls)[:2] == ["search_memory", "search_for_searches"]
    assert args_of(calls, "search_memory") == [
        {"query": "Find secreted membrane genes.", "kind": "case"}
    ]
