"""The repetition guard over PathFinder's own vocabulary.

The mechanism refuses the Nth consecutive identical read-only call and ends
the run if the model makes that call again in a later request. These cases
drive it with the tool names the agents really carry, one request per call
unless a case names a batch.
"""

from __future__ import annotations

from assistant_core.capabilities.repetition_guard import (
    DEFAULT_REPETITION_THRESHOLD,
)

from pathfinder.ai.agents.tool_vocabulary import build_tool_repetition_guard


def test_first_call_proceeds() -> None:
    guard = build_tool_repetition_guard()
    assert guard.check("get_strategy", {}, run_step=1) is None


def test_two_consecutive_identical_calls_proceed() -> None:
    guard = build_tool_repetition_guard()
    assert guard.check("get_strategy", {}, run_step=1) is None
    assert guard.check("get_strategy", {}, run_step=2) is None


def test_third_consecutive_identical_call_blocks() -> None:
    guard = build_tool_repetition_guard()
    for step in range(1, DEFAULT_REPETITION_THRESHOLD):
        assert guard.check("get_strategy", {}, run_step=step) is None

    block = guard.check("get_strategy", {}, run_step=DEFAULT_REPETITION_THRESHOLD)

    assert block is not None
    assert block.escalated is False
    assert "loop" in block.message.lower()
    assert guard.total_blocked == 1


def test_the_first_block_leaves_the_run_going() -> None:
    guard = build_tool_repetition_guard()
    for step in range(1, DEFAULT_REPETITION_THRESHOLD + 1):
        guard.check("get_strategy", {}, tool_call_id="c1", run_step=step)

    assert guard.stopped_call_id == ""
    assert guard.stopped_rule is None


def test_making_the_refused_call_again_ends_the_run() -> None:
    guard = build_tool_repetition_guard()
    for step in range(1, DEFAULT_REPETITION_THRESHOLD + 1):
        guard.check("get_strategy", {}, tool_call_id="c1", run_step=step)

    block = guard.check(
        "get_strategy",
        {},
        tool_call_id="c2",
        run_step=DEFAULT_REPETITION_THRESHOLD + 1,
    )

    assert block is not None
    assert block.escalated is True
    assert "stops here" in block.message
    assert guard.stopped_call_id == "c2"
    assert guard.stopped_rule == "identical_arguments"


def test_changing_args_resets_counter() -> None:
    guard = build_tool_repetition_guard()
    assert guard.check("get_strategy", {}, run_step=1) is None
    assert guard.check("get_strategy", {"graph_id": "g1"}, run_step=2) is None
    assert guard.check("get_strategy", {"graph_id": "g2"}, run_step=3) is None


def test_interleaved_calls_do_not_block() -> None:
    """Only consecutive identical calls trip the guard."""
    guard = build_tool_repetition_guard()
    assert guard.check("get_strategy", {}, run_step=1) is None
    assert guard.check("search_memory", {"q": "a"}, run_step=2) is None
    assert guard.check("get_strategy", {}, run_step=3) is None
    assert guard.check("search_memory", {"q": "b"}, run_step=4) is None
    assert guard.check("get_strategy", {}, run_step=5) is None


def test_a_state_changing_tool_resets_counter() -> None:
    guard = build_tool_repetition_guard()
    for step in range(1, DEFAULT_REPETITION_THRESHOLD):
        guard.check("get_strategy", {}, run_step=step)
    assert guard.check("update_leaf_params", {"step_id": "s1"}, run_step=3) is None
    assert guard.check("get_strategy", {}, run_step=4) is None
    assert guard.check("get_strategy", {}, run_step=5) is None


def test_changing_args_on_readonly_resets_counter() -> None:
    guard = build_tool_repetition_guard()
    for step in range(1, DEFAULT_REPETITION_THRESHOLD):
        assert guard.check("get_estimated_size", {}, run_step=step) is None
    one = {"wdk_step_id": 1}
    assert guard.check("get_estimated_size", one, run_step=3) is None
    assert guard.check("get_estimated_size", one, run_step=4) is None
    assert guard.check("get_estimated_size", one, run_step=5) is not None


def test_unclassified_tool_resets_counter() -> None:
    """A tool outside the vocabulary counts as progress."""
    guard = build_tool_repetition_guard()
    guard.check("get_strategy", {}, run_step=1)
    guard.check("get_strategy", {}, run_step=2)
    assert guard.check("set_criterion", {"criterion_id": "c1"}, run_step=3) is None
    assert guard.check("get_strategy", {}, run_step=4) is None
    assert guard.check("get_strategy", {}, run_step=5) is None


def test_identical_calls_of_one_batch_are_refused_and_leave_the_run_going() -> None:
    """A batch holds no request after the refusal, so the model has not read it."""
    guard = build_tool_repetition_guard()
    blocks = [
        guard.check("get_strategy", {}, tool_call_id=f"c{i}", run_step=1)
        for i in range(DEFAULT_REPETITION_THRESHOLD + 2)
    ]

    assert [block is not None for block in blocks] == [False, False, True, True, True]
    assert guard.stopped_call_id == ""
