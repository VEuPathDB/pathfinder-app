"""The read budgets one run may spend on the discovery and research tools."""

from __future__ import annotations

from pathfinder.ai.agents.tool_vocabulary import build_tool_repetition_guard
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


def test_the_guard_leaves_record_reads_to_the_reading_tool() -> None:
    guard = build_tool_repetition_guard()
    batch = [
        guard.check(
            "read_gene_record",
            {"gene_id": f"PF3D7_{i:07d}"},
            tool_call_id=f"read-{i}",
            run_step=2,
        )
        for i in range(SAMPLED_GENE_LIMIT + 2)
    ]

    assert batch == [None] * (SAMPLED_GENE_LIMIT + 2)


def _identical_calls(tool: str, args: dict[str, object], count: int) -> list[str]:
    guard = build_tool_repetition_guard()
    return [
        "" if block is None else block.message
        for block in (
            guard.check(tool, args, tool_call_id=f"c{i}", run_step=2)
            for i in range(count)
        )
    ]


def test_a_third_identical_control_test_on_one_step_is_refused() -> None:
    answered = _identical_calls(
        "run_control_tests_on_step",
        {"wdk_step_id": 441031123, "control_set_id": "set-1"},
        4,
    )

    assert answered[:2] == ["", ""]
    assert answered[2].startswith(
        "You have called run_control_tests_on_step 3 times with identical arguments"
    )
    assert answered[3].startswith(
        "You have called run_control_tests_on_step 4 times with identical arguments"
    )


def test_a_third_identical_step_id_read_is_refused() -> None:
    answered = _identical_calls("read_step_ids", {"wdk_step_id": 441031123}, 3)

    assert answered[:2] == ["", ""]
    assert answered[2].startswith(
        "You have called read_step_ids 3 times with identical arguments"
    )
