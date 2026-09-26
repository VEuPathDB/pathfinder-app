"""A fault token inserts its wrong call once, then the arc goes on."""

from __future__ import annotations

from dataclasses import replace

import pytest
from assistant_core.models.scripted import scripted_call
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    UserPromptPart,
)

from pathfinder.ai.models.mock import faults
from pathfinder.ai.models.mock.arc import history_free
from pathfinder.ai.models.mock.faults import Fault
from pathfinder.tests.unit.ai.models._mock_turns import Scene, names, play

_WRONG = {"section": "verification"}


def _wrong_read(_intended: ToolCallPart) -> ToolCallPart:
    return scripted_call("read_ledger_section", _WRONG)


@pytest.fixture
def stub_fault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        faults.FAULTS, "stub", Fault("lead", history_free(lambda: _wrong_read))
    )


@pytest.mark.usefixtures("stub_fault")
def test_the_wrong_call_comes_first_and_once_when_it_is_refused() -> None:
    calls = play(
        "lead",
        "plasmodb",
        "[[arc:recap]][[fault:stub]]",
        scene=Scene(refused={"read_ledger_section": "That section is not open yet."}),
    )

    assert names(calls) == [
        "read_ledger_section",
        "read_ledger_section",
        "get_live_strategy_state",
        "final_result",
    ]
    assert calls[0].args_as_dict() == _WRONG
    assert calls[1].args_as_dict() == {"section": "frame"}


@pytest.mark.usefixtures("stub_fault")
def test_the_arc_goes_on_after_a_wrong_call_that_answered() -> None:
    calls = play("lead", "plasmodb", "[[arc:off-topic]][[fault:stub]]")

    assert names(calls) == [
        "read_ledger_section",
        "classify_user_intent",
        "final_result",
    ]


@pytest.mark.usefixtures("stub_fault")
def test_a_fault_of_another_role_leaves_this_role_alone() -> None:
    calls = play(
        "frame",
        "plasmodb",
        "[[arc:single]][[fault:stub]]",
        work_order="Frame work order: mock frame",
    )

    assert names(calls)[0] == "search_for_searches"


def test_a_refusal_the_run_carries_twice_counts_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        faults.FAULTS, "twice", Fault("lead", history_free(lambda: _wrong_read), 2)
    )
    wrong = scripted_call("read_ledger_section", _WRONG)
    call_id = f"fault_{wrong.tool_call_id}"
    refusal = RetryPromptPart(
        content="refused", tool_name="read_ledger_section", tool_call_id=call_id
    )
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="[[arc:recap]][[fault:twice]]")]),
        ModelResponse(parts=[replace(wrong, tool_call_id=call_id)]),
        ModelRequest(parts=[refusal]),
        ModelRequest(parts=[refusal]),
    ]

    again = faults.fault_call("twice", "lead", history, wrong)

    assert again is not None
    assert again.args_as_dict() == _WRONG
