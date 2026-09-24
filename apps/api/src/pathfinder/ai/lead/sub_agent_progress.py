"""What one sub-agent dispatch reports while it runs.

The running token and cost card, the context-fill reading behind it, the
ledger snapshot after each inner tool call, and the usage a run that ended
without a result still owes the turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from assistant_core.conversation.stream_parts.agent_topology import (
    SubAgentCallPayload,
    sub_agent_call_event,
)
from assistant_core.cost import cost_for_run
from assistant_core.graph.emit import emit_chunk
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.stream_events import ledger_update_event
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import (
    WIRE_PHASE_BY_ROLE,
    LeadDeps,
    SubAgentCallUsage,
    SubAgentRunUsage,
    apply_agent_state,
    phase_model_id,
)
from pathfinder.ai.models.catalog import context_window_for
from pathfinder.platform.model_keys import turn_paid_by

__all__ = [
    "ContextMeter",
    "emit_live_ledger",
    "emit_running_usage",
    "record_stopped_usage",
    "run_usage",
]


def run_usage(
    event: AgentRunResultEvent[Any],
    deps: LeadDeps,
    role: PhaseRole,
    parent_tool_call_id: str,
) -> SubAgentRunUsage:
    """What one finished sub-agent run spent, as the dispatch records it."""
    response = event.result.response
    return SubAgentRunUsage(
        usage=event.result.usage,
        model_name=response.model_name,
        provider_name=response.provider_name,
        provider_url=response.provider_url,
        parent_tool_call_id=parent_tool_call_id,
        paid_by=turn_paid_by(phase_model_id(deps.runtime, role)),
    )


def record_stopped_usage(
    deps: LeadDeps,
    role: PhaseRole,
    parent_tool_call_id: str,
    usage: RunUsage,
) -> None:
    """Record usage for a run that ended without a result event.

    A stop yields no result, so the turn's totals would otherwise drop the
    run's tokens. The run is priced on the model the stage ran.
    """
    model_id = phase_model_id(deps.runtime, role)
    provider, _, model = model_id.partition(":")
    deps.record_sub_agent_usage(
        SubAgentRunUsage(
            usage=usage,
            model_name=model or None,
            provider_name=provider or None,
            provider_url=None,
            parent_tool_call_id=parent_tool_call_id,
            paid_by=turn_paid_by(model_id),
        ),
    )


@dataclass
class ContextMeter:
    """The model one dispatch runs, and the input tokens already reported for it.

    ``RunUsage.input_tokens`` accumulates over a run, so one request's input
    size is the delta between two readings. One request answers every one of
    its parallel tool calls, so an unchanged reading repeats the last size
    instead of reporting 0. A drop reads as 0.
    """

    model_id: str
    seen_input: int = 0
    last_size: int = 0

    def last_request_input(self, usage: RunUsage) -> int:
        delta = usage.input_tokens - self.seen_input
        self.seen_input = usage.input_tokens
        if delta > 0:
            self.last_size = delta
        elif delta < 0:
            self.last_size = 0
        return self.last_size


def emit_running_usage(
    writer: Any,
    role: PhaseRole,
    parent_tool_call_id: str,
    usage: RunUsage,
    meter: ContextMeter,
    *,
    baseline: SubAgentCallUsage,
) -> None:
    """Push the dispatch's running tokens/cost and context fill after each
    inner tool call, priced on the model the meter reads. ``baseline`` is what
    its earlier passes spent."""
    model_id = meter.model_id
    provider, _, model = model_id.partition(":")
    cost = baseline.cost + cost_for_run(
        usage=usage,
        model_name=model or None,
        provider_name=provider or None,
        provider_url=None,
    )
    emit_chunk(
        writer,
        sub_agent_call_event(
            SubAgentCallPayload(
                tool_call_id=parent_tool_call_id,
                sub_agent=role,
                phase=WIRE_PHASE_BY_ROLE[role],
                state="started",
                model_id=model_id,
                tokens=baseline.tokens + usage.total_tokens,
                cost_usd=str(cost),
                context_tokens=meter.last_request_input(usage),
                context_window=context_window_for(model_id),
            )
        ),
    )


def emit_live_ledger(
    writer: Any,
    deps: LeadDeps,
    agent_deps: AgentDeps,
) -> None:
    """Sync state and broadcast a ledger snapshot after a sub-agent tool call."""
    apply_agent_state(deps, agent_deps)
    ledger = derive_ledger(deps.state, deps.intent)
    emit_chunk(writer, ledger_update_event(ledger=ledger))
