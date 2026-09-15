"""The reply a guard-stopped turn writes names the rule that stopped it."""

from __future__ import annotations

from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from pydantic_ai.messages import FunctionToolResultEvent, ToolReturnPart
from pydantic_ai.usage import RunUsage

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import loop_stop_prose
from pathfinder.ai.graph.lead_node import _stream_ends_after
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

LITERATURE = "research_literature_search"


def _stopped_by(guard: ToolRepetitionGuard, calls: list[dict[str, str]]) -> str:
    """Drive the guard through the calls and return the refusal that stops the run."""
    message = ""
    for i, args in enumerate(calls):
        block = guard.check(LITERATURE, args, tool_call_id=f"c{i}")
        if block is not None and block.escalated:
            message = block.message
    assert guard.stopped_call_id != ""
    return message


def _reply_after(guard: ToolRepetitionGuard, refusal: str) -> str:
    deps = lead_deps(
        pipeline_state(user_prompt="What is known about the Giardia mitosome?")
    )
    capture = _LeadRunCapture()
    event = FunctionToolResultEvent(
        part=ToolReturnPart(
            tool_name=LITERATURE,
            content=refusal,
            tool_call_id=guard.stopped_call_id,
        ),
    )

    assert _stream_ends_after(event, guard, capture, RunUsage(), deps) is True
    return loop_stop_prose(capture.guard_stop)


def test_a_run_stopped_at_a_tool_budget_says_so() -> None:
    guard = ToolRepetitionGuard(
        read_only_tools=frozenset({LITERATURE}), call_caps={LITERATURE: 2}
    )
    refusal = _stopped_by(guard, [{"query": f"distinct query {i}"} for i in range(4)])

    assert _reply_after(guard, refusal) == (
        "I stopped this turn: I read research_literature_search past its budget "
        "for one turn without settling the answer. Ask me to continue and I will "
        "answer from what it returned, or narrow the question."
    )


def test_a_run_stopped_on_a_repeated_call_says_so() -> None:
    guard = ToolRepetitionGuard(read_only_tools=frozenset({LITERATURE}), threshold=2)
    refusal = _stopped_by(guard, [{"query": "the same query"}] * 3)

    assert _reply_after(guard, refusal) == (
        "I stopped this turn: I was repeating the same lookup and making "
        "no progress. Tell me what to try instead and I will carry on."
    )
