"""What a running dispatch reports: context fill, and one phase name per call."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph._lead_events import (
    _SUB_AGENT_TOOL_TO_PHASE,
    handle_sub_agent_event,
)
from pathfinder.ai.lead.deltas import RecoveryDelta
from pathfinder.ai.lead.sub_agent_stream import (
    _ContextMeter,
    _emit_running_sub_agent_usage,
)
from pathfinder.ai.lead.sub_agent_tools import SubAgentCallUsage
from pathfinder.ai.models.catalog import get_model_entry
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
)

_WIRE_PHASES = frozenset({"frame", "build", "verification"})
_CALL_ID = "sa_1"


def test_context_meter_reports_each_request_input_delta() -> None:
    meter = _ContextMeter()
    usage = RunUsage(input_tokens=1000)

    assert meter.last_request_input(usage) == 1000

    usage.input_tokens = 2500
    assert meter.last_request_input(usage) == 1500


def test_context_meter_floors_a_reset_at_zero() -> None:
    """A history reset lowers the cumulative count; the bar reads zero."""
    meter = _ContextMeter()
    usage = RunUsage(input_tokens=5000)
    meter.last_request_input(usage)

    usage.input_tokens = 3000
    assert meter.last_request_input(usage) == 0


def test_context_meter_repeats_the_size_across_one_requests_emissions() -> None:
    """Parallel tool calls emit twice for one request; the bar must not drop."""
    meter = _ContextMeter()
    usage = RunUsage(input_tokens=1000)

    assert meter.last_request_input(usage) == 1000
    assert meter.last_request_input(usage) == 1000

    usage.input_tokens = 2500
    assert meter.last_request_input(usage) == 1500


def test_running_emission_carries_the_last_request_and_the_window() -> None:
    collector = ChunkCollector()
    meter = _ContextMeter()
    usage = RunUsage(input_tokens=1000, output_tokens=10)

    _emit_running_sub_agent_usage(
        collector, "frame", "call_frame_1", usage, meter, baseline=SubAgentCallUsage()
    )
    usage.input_tokens = 2500
    _emit_running_sub_agent_usage(
        collector, "frame", "call_frame_1", usage, meter, baseline=SubAgentCallUsage()
    )

    first, second = collector.data_of("data-sub-agent-call")
    assert first["contextTokens"] == 1000
    assert second["contextTokens"] == 1500
    entry = get_model_entry(first["modelId"])
    assert entry is not None
    assert first["contextWindow"] == entry.context_size
    assert second["contextWindow"] == entry.context_size


def test_a_continued_pass_adds_to_what_the_dispatch_already_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card reads the dispatch, not the pass that is running right now."""
    collector = ChunkCollector()
    monkeypatch.setattr(
        "pathfinder.ai.lead.sub_agent_stream.phase_default_model_id",
        lambda role: "nosuchprovider:nosuchmodel",
    )

    _emit_running_sub_agent_usage(
        collector,
        "frame",
        _CALL_ID,
        RunUsage(input_tokens=54),
        _ContextMeter(),
        baseline=SubAgentCallUsage(tokens=2441, cost=Decimal("0.00841")),
    )

    payload = collector.data_of("data-sub-agent-call")[0]
    assert payload["tokens"] == 2495
    assert payload["costUsd"] == "0.00841"


def test_unknown_model_reports_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = ChunkCollector()
    monkeypatch.setattr(
        "pathfinder.ai.lead.sub_agent_stream.phase_default_model_id",
        lambda role: "nosuchprovider:nosuchmodel",
    )

    _emit_running_sub_agent_usage(
        collector,
        "frame",
        "call_frame_1",
        RunUsage(input_tokens=900),
        _ContextMeter(),
        baseline=SubAgentCallUsage(),
    )

    payload = collector.data_of("data-sub-agent-call")[0]
    assert payload["contextWindow"] == 0
    assert payload["contextTokens"] == 900


@pytest.mark.parametrize(
    ("tool_name", "role"),
    [
        ("frame_problem", "frame"),
        ("edit_strategy", "frame"),
        ("recover_failed_steps", "execution"),
        ("verify_strategy", "verification"),
    ],
)
def test_one_call_id_carries_one_phase_name(
    tool_name: str,
    role: PhaseRole,
) -> None:
    collector = ChunkCollector()
    deps = lead_deps(pipeline_state(user_prompt="recover the failed steps"))
    calls: dict[str, str] = {}

    handle_sub_agent_event(
        deps,
        collector,
        FunctionToolCallEvent(
            part=ToolCallPart(
                tool_name=tool_name,
                args={"reason": "why"},
                tool_call_id=_CALL_ID,
            ),
        ),
        calls,
        {},
    )
    _emit_running_sub_agent_usage(
        collector,
        role,
        _CALL_ID,
        RunUsage(),
        _ContextMeter(),
        baseline=SubAgentCallUsage(),
    )
    handle_sub_agent_event(
        deps,
        collector,
        FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name=tool_name,
                content=RecoveryDelta(),
                tool_call_id=_CALL_ID,
            ),
        ),
        calls,
        {},
    )

    phases = {
        data["phase"]
        for data in collector.data_of("data-sub-agent-call")
        if data["toolCallId"] == _CALL_ID
    }
    assert len(phases) == 1, phases
    assert phases <= _WIRE_PHASES


def test_the_wire_vocabulary_is_frame_build_and_verification() -> None:
    assert set(_SUB_AGENT_TOOL_TO_PHASE.values()) == _WIRE_PHASES
