"""The Lead's usage chunk carries the last request's input size and its window."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from assistant_core import quota
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph._lead_capture import (
    _charge_token_delta,
    _LeadRunCapture,
    emit_lead_usage,
)
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.models.catalog import context_window_for
from pathfinder.domain.strategy.session import StrategySession

_LEAD_MODEL = "openai:gpt-5.6-luna"


class _Collector:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)

    @property
    def lead_usage(self) -> list[dict[str, Any]]:
        return [
            p["chunk"]["data"]
            for p in self.payloads
            if p["chunk"]["type"] == "data-lead-usage"
        ]


class _FakeSession:
    async def commit(self) -> None:
        return None


@asynccontextmanager
async def _session_factory() -> AsyncIterator[Any]:
    yield _FakeSession()


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find kinases.",
    )


def _context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=_session_factory,
        cancel_event=asyncio.Event(),
    )


@pytest.fixture
def no_quota_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _accumulate(
        session: AsyncSession,
        *,
        user_id: Any,
        tokens: int,
        cost_usd: Decimal,
    ) -> None:
        del session, user_id, tokens, cost_usd

    monkeypatch.setattr(quota, "accumulate", _accumulate)


def test_context_window_for_reads_the_catalog() -> None:
    assert context_window_for(_LEAD_MODEL) > 0
    assert context_window_for("nosuchprovider:nosuchmodel") == 0


@pytest.mark.asyncio
async def test_each_charged_delta_records_the_request_input(
    no_quota_writes: None,
) -> None:
    capture = _LeadRunCapture()
    capture.lead_model = _LEAD_MODEL
    state = _state()
    context = _context()
    collector = _Collector()
    usage = RunUsage(input_tokens=1200, output_tokens=20)

    await _charge_token_delta(context, state, capture, usage, collector, _LEAD_MODEL)
    assert capture.last_request_input_tokens == 1200

    usage.input_tokens = 3000
    usage.output_tokens = 45
    await _charge_token_delta(context, state, capture, usage, collector, _LEAD_MODEL)
    assert capture.last_request_input_tokens == 1800

    first, second = collector.lead_usage
    assert first["contextTokens"] == 1200
    assert second["contextTokens"] == 1800
    assert second["contextWindow"] == context_window_for(_LEAD_MODEL)


def test_lead_usage_event_carries_zero_when_nothing_was_charged() -> None:
    collector = _Collector()

    emit_lead_usage(
        collector,
        "nosuchprovider:nosuchmodel",
        0,
        "0",
        context_tokens=0,
        context_window=0,
    )

    payload = collector.lead_usage[0]
    assert payload["contextTokens"] == 0
    assert payload["contextWindow"] == 0
