"""The read budgets one run may spend on the discovery and research tools."""

from __future__ import annotations

from pathfinder.ai.agents.tool_vocabulary import (
    build_tool_repetition_guard,
    build_verification_repetition_guard,
)
from pathfinder.domain.evidence import SAMPLED_GENE_LIMIT


def _distinct_calls(tool: str, count: int) -> list[str | None]:
    guard = build_tool_repetition_guard()
    return [
        None if block is None else block.rule
        for block in (
            guard.check(
                tool, {"query": f"query {i}"}, tool_call_id=f"c{i}", run_step=i + 1
            )
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


def test_a_check_that_reads_ten_records_in_one_batch_is_refused_twice_and_goes_on() -> (
    None
):
    guard = build_verification_repetition_guard()
    batch = [
        guard.check(
            "read_gene_record",
            {"gene_id": f"PF3D7_{i:07d}"},
            tool_call_id=f"read-{i}",
            run_step=2,
        )
        for i in range(SAMPLED_GENE_LIMIT + 2)
    ]

    refused = [block for block in batch if block is not None]
    assert [block.count for block in refused] == [9, 10]
    assert [block.escalated for block in refused] == [False, False]
    assert guard.stopped_call_id == ""


def test_the_next_request_that_reads_a_record_past_the_budget_stops_the_check() -> None:
    guard = build_verification_repetition_guard()
    for i in range(SAMPLED_GENE_LIMIT + 2):
        guard.check(
            "read_gene_record",
            {"gene_id": f"PF3D7_{i:07d}"},
            tool_call_id=f"read-{i}",
            run_step=2,
        )

    block = guard.check(
        "read_gene_record",
        {"gene_id": "PF3D7_0000099"},
        tool_call_id="read-late",
        run_step=3,
    )

    assert block is not None
    assert block.escalated is True
    assert guard.stopped_call_id == "read-late"
    assert guard.stopped_rule == "call_cap"
