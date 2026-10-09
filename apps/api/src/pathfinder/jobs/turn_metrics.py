from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from assistant_core.conversation.event_writer import ChatWriter
from assistant_core.conversation.stream_parts.agent_topology import (
    LeadUsagePayload,
    SubAgentCallPayload,
)
from assistant_core.platform.types import PaidBy
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from pathfinder.platform.metrics import (
    CHAT_TURN_DURATION,
    CHAT_TURNS_FINISHED,
    MODEL_COST_USD,
    MODEL_TOKENS,
)
from pathfinder.platform.model_catalog import get_model_entry
from pathfinder.platform.model_keys import turn_paid_by

__all__ = ["MeteredWriter", "metered_turn"]


class _Chunk(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    type: str = ""
    id: str = ""
    finish_reason: str | None = Field(default=None, alias="finishReason")
    data: dict[str, JsonValue] = Field(default_factory=dict)


class _TurnUsage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    total_tokens: int = Field(default=0, alias="totalTokens")
    cost_usd: Decimal = Field(default=Decimal(0), alias="costUsd")


@dataclass(frozen=True)
class _Spend:
    model: str
    tokens: int
    cost_usd: Decimal
    payer: PaidBy


@dataclass
class _Observed:
    finish_reason: str = ""
    stopped: bool = False
    raised: bool = False
    by_agent: dict[str, _Spend] = field(default_factory=dict)
    turn_total: _Spend | None = None

    @property
    def outcome(self) -> str:
        if self.stopped:
            return "stopped"
        if self.raised or self.finish_reason == "error":
            return "failed"
        return "completed"

    def spends(self) -> list[_Spend]:
        named = list(self.by_agent.values())
        total = self.turn_total
        if total is None:
            return named
        rest_tokens = total.tokens - sum(spend.tokens for spend in named)
        rest_cost = total.cost_usd - sum(
            (spend.cost_usd for spend in named), Decimal(0)
        )
        if rest_tokens <= 0 and rest_cost <= 0:
            return named
        rest = _Spend(
            total.model, max(rest_tokens, 0), max(rest_cost, Decimal(0)), total.payer
        )
        return [*named, rest]


@dataclass
class MeteredWriter:
    inner: ChatWriter
    model_id: str
    conversation_id: UUID = field(init=False)
    turn_id: UUID = field(init=False)
    observed: _Observed = field(default_factory=_Observed, init=False)

    def __post_init__(self) -> None:
        self.conversation_id = self.inner.conversation_id
        self.turn_id = self.inner.turn_id

    async def write(self, chunk: dict[str, Any]) -> int:
        self._observe(_Chunk.model_validate(chunk))
        return await self.inner.write(chunk)

    def _spend(self, model: str, tokens: int, cost_usd: str | Decimal) -> _Spend:
        named = model or self.model_id
        return _Spend(named, tokens, Decimal(cost_usd), turn_paid_by(named))

    def _observe(self, chunk: _Chunk) -> None:
        observed = self.observed
        match chunk.type:
            case "finish":
                observed.finish_reason = chunk.finish_reason or ""
            case "data-turn-stopped":
                observed.stopped = True
            case "data-lead-usage":
                lead = LeadUsagePayload.model_validate(chunk.data)
                observed.by_agent[chunk.id] = self._spend(
                    lead.model_id, lead.tokens, lead.cost_usd
                )
            case "data-sub-agent-call":
                call = SubAgentCallPayload.model_validate(chunk.data)
                observed.by_agent[chunk.id] = self._spend(
                    call.model_id, call.tokens, call.cost_usd
                )
            case "data-turn-usage":
                usage = _TurnUsage.model_validate(chunk.data)
                observed.turn_total = self._spend(
                    self.model_id, usage.total_tokens, usage.cost_usd
                )


_OTHER_MODEL = "other"


def _model_label(model_id: str) -> str:
    return model_id if get_model_entry(model_id) is not None else _OTHER_MODEL


def _record(assistant_id: str, writer: MeteredWriter, seconds: float) -> None:
    outcome = writer.observed.outcome
    CHAT_TURNS_FINISHED.labels(
        assistant_id, outcome, _model_label(writer.model_id)
    ).inc()
    CHAT_TURN_DURATION.labels(assistant_id, outcome).observe(seconds)
    for spend in writer.observed.spends():
        model, payer = _model_label(spend.model), spend.payer.value
        MODEL_TOKENS.labels(model, payer).inc(spend.tokens)
        MODEL_COST_USD.labels(model, payer).inc(float(spend.cost_usd))


@asynccontextmanager
async def metered_turn(
    *, assistant_id: str, model_id: str, writer: ChatWriter
) -> AsyncIterator[MeteredWriter]:
    metered = MeteredWriter(inner=writer, model_id=model_id)
    started = time.monotonic()
    try:
        yield metered
    except BaseException:
        metered.observed.raised = True
        raise
    finally:
        _record(assistant_id, metered, time.monotonic() - started)
