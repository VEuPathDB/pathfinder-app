"""A durable call in a process that reaches no worker is answered, not parked."""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.tasks.declaration import declared_durable_tools
from pydantic_ai.messages import ModelMessage, ToolReturnPart

from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.devtools.capture import RESULT_CLIP
from pathfinder.platform.durable_worker import (
    deferring_tool_names,
    durable_call_refusal,
    no_durable_worker,
)
from pathfinder.tests._support.durable_dispatch import capture_durable_dispatch
from pathfinder.tests.unit.ai.capabilities.test_agent_failure_seams import (
    _VERIFY_OUTPUT,
    _agent_deps,
    _calls_then_answers,
)

_CONTROL_TESTS = "run_control_tests_on_step"
_ARGS: dict[str, Any] = {
    "wdk_step_id": 132,
    "positive_controls": ["TGME49_201780"],
}


def _tool_returns(messages: list[ModelMessage], tool_name: str) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == tool_name
    ]


async def test_a_durable_call_with_no_worker_is_answered_in_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The turn finishes, and the transcript says which tool was declined."""
    dispatch = capture_durable_dispatch(monkeypatch)
    agent = build_verification_agent()
    model = _calls_then_answers(_CONTROL_TESTS, _ARGS, _VERIFY_OUTPUT)

    with no_durable_worker(), agent.override(model=model):
        result = await agent.run("verify it", deps=_agent_deps())

    (answered,) = _tool_returns(list(result.all_messages()), _CONTROL_TESTS)
    assert answered.content == durable_call_refusal(_CONTROL_TESTS)
    assert dispatch.created == []
    assert dispatch.deferred == []


async def test_a_durable_call_still_reaches_the_worker_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal is the debugger's, so a served turn defers as it always did."""
    dispatch = capture_durable_dispatch(monkeypatch)
    agent = build_verification_agent()
    model = _calls_then_answers(_CONTROL_TESTS, _ARGS, _VERIFY_OUTPUT)

    with agent.override(model=model):
        await agent.run("verify it", deps=_agent_deps())

    assert [row["tool_name"] for row in dispatch.created] == [_CONTROL_TESTS]
    assert len(dispatch.deferred) == 1


def test_every_declared_durable_tool_defers_under_a_recorded_name() -> None:
    """A tool recorded under the job name would be parked, not answered."""
    assert dict(deferring_tool_names()) == {
        "run_control_tests_on_step": "run_control_tests_on_step",
        "optimize_search_parameters": "optimize_search_parameters",
        "run_eda_compute": "run_eda_compute",
        "separate_controls": "separate_controls",
    }
    assert set(deferring_tool_names().values()) == {
        tool.tool_name for tool in declared_durable_tools()
    }


def test_the_refusal_says_what_it_says() -> None:
    """The model reads this sentence in place of the call, so it is pinned."""
    assert durable_call_refusal("run_eda_compute") == (
        "run_eda_compute runs on a worker this process cannot reach. Nothing "
        "started. Say it was not available and report what you have."
    )


def test_every_refusal_fits_the_line_a_run_transcript_prints() -> None:
    """A clipped refusal loses the instruction at its end."""
    longest = max(
        (tool.tool_name for tool in declared_durable_tools()),
        key=len,
    )

    assert len(durable_call_refusal(longest)) <= RESULT_CLIP
