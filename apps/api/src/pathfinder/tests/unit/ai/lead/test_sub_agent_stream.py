"""What a running dispatch reports: context fill, and one phase name per call."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel
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
from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.deltas import (
    EditDelta,
    FrameResult,
    RecoveryDelta,
    VerificationDelta,
)
from pathfinder.ai.lead.sub_agent_progress import (
    ContextMeter,
    emit_running_usage,
)
from pathfinder.ai.lead.sub_agent_tools import SubAgentCallUsage
from pathfinder.ai.models.catalog import get_model_entry
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
)

_WIRE_PHASES = frozenset({"frame", "build", "verification"})
_CALL_ID = "sa_1"


def test_context_meter_reports_each_request_input_delta() -> None:
    meter = ContextMeter()
    usage = RunUsage(input_tokens=1000)

    assert meter.last_request_input(usage) == 1000

    usage.input_tokens = 2500
    assert meter.last_request_input(usage) == 1500


def test_context_meter_floors_a_reset_at_zero() -> None:
    """A history reset lowers the cumulative count; the bar reads zero."""
    meter = ContextMeter()
    usage = RunUsage(input_tokens=5000)
    meter.last_request_input(usage)

    usage.input_tokens = 3000
    assert meter.last_request_input(usage) == 0


def test_context_meter_repeats_the_size_across_one_requests_emissions() -> None:
    """Parallel tool calls emit twice for one request; the bar must not drop."""
    meter = ContextMeter()
    usage = RunUsage(input_tokens=1000)

    assert meter.last_request_input(usage) == 1000
    assert meter.last_request_input(usage) == 1000

    usage.input_tokens = 2500
    assert meter.last_request_input(usage) == 1500


def test_running_emission_carries_the_last_request_and_the_window() -> None:
    collector = ChunkCollector()
    meter = ContextMeter()
    usage = RunUsage(input_tokens=1000, output_tokens=10)

    emit_running_usage(
        collector, "frame", "call_frame_1", usage, meter, baseline=SubAgentCallUsage()
    )
    usage.input_tokens = 2500
    emit_running_usage(
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
        "pathfinder.ai.lead.sub_agent_progress.phase_default_model_id",
        lambda role: "nosuchprovider:nosuchmodel",
    )

    emit_running_usage(
        collector,
        "frame",
        _CALL_ID,
        RunUsage(input_tokens=54),
        ContextMeter(),
        baseline=SubAgentCallUsage(tokens=2441, cost=Decimal("0.00841")),
    )

    payload = collector.data_of("data-sub-agent-call")[0]
    assert payload["tokens"] == 2495
    assert payload["costUsd"] == "0.00841"


def test_unknown_model_reports_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = ChunkCollector()
    monkeypatch.setattr(
        "pathfinder.ai.lead.sub_agent_progress.phase_default_model_id",
        lambda role: "nosuchprovider:nosuchmodel",
    )

    emit_running_usage(
        collector,
        "frame",
        "call_frame_1",
        RunUsage(input_tokens=900),
        ContextMeter(),
        baseline=SubAgentCallUsage(),
    )

    payload = collector.data_of("data-sub-agent-call")[0]
    assert payload["contextWindow"] == 0
    assert payload["contextTokens"] == 900


_PASSED = VerificationDigest(
    disposition=PhaseDisposition.DONE, prose="61 genes.", reason="ok", success=True
)


@pytest.mark.parametrize(
    ("tool_name", "role", "delta"),
    [
        ("frame_problem", "frame", FrameResult()),
        ("edit_strategy", "frame", EditDelta(diff=SpecDiff())),
        ("recover_failed_steps", "execution", RecoveryDelta()),
        ("verify_strategy", "verification", VerificationDelta(digest=_PASSED)),
    ],
)
def test_one_call_id_carries_one_phase_name(
    tool_name: str,
    role: PhaseRole,
    delta: BaseModel,
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
    emit_running_usage(
        collector,
        role,
        _CALL_ID,
        RunUsage(),
        ContextMeter(),
        baseline=SubAgentCallUsage(),
    )
    handle_sub_agent_event(
        deps,
        collector,
        FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name=tool_name,
                content=delta,
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
