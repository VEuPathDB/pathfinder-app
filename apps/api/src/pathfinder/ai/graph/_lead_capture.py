"""Lead-run capture + token/cost accounting.

Shared base for the Lead node: the mutable ``_LeadRunCapture`` accumulator and
the streaming/residual quota charging that mutates it. Kept separate so
``lead_node`` and its event helpers can share this state without an import
cycle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from assistant_core import quota
from assistant_core.capabilities.repetition_guard import BlockRule
from assistant_core.conversation.stream_parts.agent_topology import lead_usage_event
from assistant_core.cost import cost_for_run
from assistant_core.graph.emit import emit_chunk, emit_turn_usage
from assistant_core.graph.turn_state import PendingApproval, PendingDurableCall
from assistant_core.platform.logging import get_logger
from pydantic_ai.messages import ModelMessage
from pydantic_ai.ui.vercel_ai.response_types import (
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
)
from pydantic_ai.usage import RunUsage
from sqlalchemy.exc import SQLAlchemyError

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import (
    SubAgentCallUsage,
    SubAgentRunUsage,
    ToolCharge,
)
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.ai.models.catalog import context_window_for

logger = get_logger(__name__)


@dataclass(frozen=True)
class GuardStop:
    """The call whose refusal ended the run, and the rule that refused it."""

    tool_name: str
    rule: BlockRule


@dataclass
class _LeadRunCapture:
    """Terminal state captured from the Lead agent's streaming run."""

    guard_stop: GuardStop | None = None
    # The text of the error chunk that ended the run, when one did.
    run_error: str | None = None

    new_messages: list[ModelMessage] = field(default_factory=list)
    finish_reason: str = "stop"
    response: LeadResponse | None = None
    tokens: int = 0
    cost_usd: Decimal = field(default_factory=lambda: Decimal(0))
    charged_input_tokens: int = 0
    charged_output_tokens: int = 0
    charged_cache_read_tokens: int = 0
    charged_cache_write_tokens: int = 0
    charged_cost: Decimal = field(default_factory=lambda: Decimal(0))
    sub_agent_tokens: int = 0
    sub_agent_cost: Decimal = field(default_factory=lambda: Decimal(0))
    tool_cost: Decimal = field(default_factory=lambda: Decimal(0))
    sub_agent_usage_by_call: dict[str, SubAgentCallUsage] = field(default_factory=dict)
    lead_model: str = ""
    last_request_input_tokens: int = 0
    pending_approval: PendingApproval | None = None
    pending_durable_call: PendingDurableCall | None = None
    parked_call_answered: bool = False
    prose_already_streamed: bool = False

    @property
    def charged_tokens(self) -> int:
        return self.charged_input_tokens + self.charged_output_tokens

    @property
    def cumulative_tokens(self) -> int:
        return self.charged_tokens + self.sub_agent_tokens

    @property
    def cumulative_cost(self) -> Decimal:
        return self.charged_cost + self.sub_agent_cost + self.tool_cost

    def live_totals(self, state: PipelineState) -> tuple[int, str]:
        """Running turn totals (base + charged-so-far) for a usage event."""
        return (
            state.turn_total_tokens + self.cumulative_tokens,
            str(state.turn_total_cost_usd + self.cumulative_cost),
        )

    def residual_totals(self, state: PipelineState) -> tuple[int, str]:
        """Final turn totals using the captured (not charged) lead tokens."""
        return (
            state.turn_total_tokens + self.tokens + self.sub_agent_tokens,
            str(
                state.turn_total_cost_usd
                + self.cost_usd
                + self.sub_agent_cost
                + self.tool_cost
            ),
        )


def absorb_sub_agent_usage(capture: _LeadRunCapture, info: SubAgentRunUsage) -> None:
    """Add one sub-agent pass to the turn total and to its dispatch's total.

    A dispatch that ran more than one pass owes the sum of them, so the card
    the thread reads carries what the turn counted for that call.
    """
    cost = cost_for_run(
        usage=info.usage,
        model_name=info.model_name,
        provider_name=info.provider_name,
        provider_url=info.provider_url,
    )
    capture.sub_agent_tokens += info.usage.total_tokens
    capture.sub_agent_cost += cost
    by_call = capture.sub_agent_usage_by_call
    spent = by_call.get(info.parent_tool_call_id, SubAgentCallUsage())
    by_call[info.parent_tool_call_id] = spent.plus(info.usage.total_tokens, cost)


def absorb_tool_charge(capture: _LeadRunCapture, charge: ToolCharge) -> None:
    """Add what one served tool call cost to the turn total."""
    capture.tool_cost += charge.cost_usd


def usage_recorders(
    capture: _LeadRunCapture,
    state: PipelineState,
    writer: Any,
) -> tuple[Callable[[SubAgentRunUsage], None], Callable[[ToolCharge], None]]:
    """The two spends outside the Lead's own calls; each reports the running total."""

    def _report() -> None:
        total_tokens, cost_usd = capture.live_totals(state)
        emit_turn_usage(writer, total_tokens, cost_usd)

    def record_sub_agent(info: SubAgentRunUsage) -> None:
        absorb_sub_agent_usage(capture, info)
        _report()

    def record_tool(charge: ToolCharge) -> None:
        absorb_tool_charge(capture, charge)
        _report()

    return record_sub_agent, record_tool


def emit_lead_usage(
    writer: Any,
    model_id: str,
    tokens: int,
    cost_usd: str,
    *,
    context_tokens: int,
    context_window: int,
) -> None:
    emit_chunk(
        writer,
        lead_usage_event(
            model_id=model_id,
            tokens=tokens,
            cost_usd=cost_usd,
            context_tokens=context_tokens,
            context_window=context_window,
        ),
    )


def _emit_residual_prose(
    writer: Any,
    capture: _LeadRunCapture,
    *,
    message_id: UUID,
) -> None:
    response = capture.response
    if response is None or not response.prose or capture.prose_already_streamed:
        return
    chunk_id = f"lead-prose-{message_id}"
    emit_chunk(writer, TextStartChunk(id=chunk_id))
    emit_chunk(writer, TextDeltaChunk(id=chunk_id, delta=response.prose))
    emit_chunk(writer, TextEndChunk(id=chunk_id))


def _split_agent_model(agent_model: str) -> tuple[str | None, str | None]:
    if ":" not in agent_model:
        return None, agent_model or None
    provider, _, model = agent_model.partition(":")
    return provider or None, model or None


async def _charge_token_delta(
    context: Context | None,
    state: PipelineState,
    capture: _LeadRunCapture,
    usage: RunUsage,
    writer: Any,
    agent_model: str,
) -> None:
    if context is None:
        return
    delta_input = usage.input_tokens - capture.charged_input_tokens
    delta_output = usage.output_tokens - capture.charged_output_tokens
    delta_cache_read = usage.cache_read_tokens - capture.charged_cache_read_tokens
    delta_cache_write = usage.cache_write_tokens - capture.charged_cache_write_tokens
    delta_tokens = delta_input + delta_output + delta_cache_read + delta_cache_write
    if delta_tokens <= 0:
        return
    provider_name, model_name = _split_agent_model(agent_model)
    delta_cost = cost_for_run(
        usage=RunUsage(
            input_tokens=delta_input,
            output_tokens=delta_output,
            cache_read_tokens=delta_cache_read,
            cache_write_tokens=delta_cache_write,
        ),
        model_name=model_name,
        provider_name=provider_name,
        provider_url=None,
    )
    try:
        async with context.db_session_factory() as session:
            await quota.accumulate(
                session,
                user_id=state.user_id,
                tokens=delta_tokens,
                cost_usd=delta_cost,
            )
            await session.commit()
    except SQLAlchemyError:
        logger.warning(
            "failed to accumulate streaming token delta",
            user_id=str(state.user_id),
            conversation_id=str(state.conversation_id),
            delta=delta_tokens,
        )
        return
    capture.charged_input_tokens += delta_input
    capture.charged_output_tokens += delta_output
    capture.charged_cache_read_tokens += delta_cache_read
    capture.charged_cache_write_tokens += delta_cache_write
    capture.charged_cost += delta_cost
    if delta_input > 0:
        # ``input_tokens`` accumulates over the run, so one request's input
        # size is the delta. A charge with no new input keeps the last size.
        capture.last_request_input_tokens = delta_input
    total_tokens, cost_usd = capture.live_totals(state)
    emit_turn_usage(writer, total_tokens, cost_usd)
    emit_lead_usage(
        writer,
        capture.lead_model,
        capture.charged_tokens,
        str(capture.charged_cost),
        context_tokens=capture.last_request_input_tokens,
        context_window=context_window_for(capture.lead_model),
    )


async def _persist_residual_quota(
    context: Context | None,
    state: PipelineState,
    capture: _LeadRunCapture,
) -> None:
    if context is None:
        return
    lead_residual_tokens = max(capture.tokens - capture.charged_tokens, 0)
    lead_residual_cost = max(capture.cost_usd - capture.charged_cost, Decimal(0))
    sub_agent_tokens = capture.sub_agent_tokens
    sub_agent_cost = capture.sub_agent_cost
    total_tokens = lead_residual_tokens + sub_agent_tokens
    total_cost = lead_residual_cost + sub_agent_cost + capture.tool_cost
    if total_tokens == 0 and total_cost == 0:
        return
    async with context.db_session_factory() as session:
        try:
            await quota.accumulate(
                session,
                user_id=state.user_id,
                tokens=total_tokens,
                cost_usd=total_cost,
            )
            capture.charged_output_tokens += lead_residual_tokens
            capture.charged_cost += lead_residual_cost
            capture.sub_agent_tokens = 0
            capture.sub_agent_cost = Decimal(0)
            capture.tool_cost = Decimal(0)
        except SQLAlchemyError:
            logger.warning(
                "failed to accumulate lead residual quota",
                user_id=str(state.user_id),
                conversation_id=str(state.conversation_id),
            )
        await session.commit()
