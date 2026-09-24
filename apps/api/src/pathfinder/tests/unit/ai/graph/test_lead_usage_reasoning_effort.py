"""The Lead's usage chunk names the reasoning effort the turn ran under."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from assistant_core import quota
from assistant_core.platform.types import PaidBy
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph._lead_capture import (
    _charge_token_delta,
    _LeadRunCapture,
    emit_lead_usage,
)
from pathfinder.ai.graph._lead_model import resolve_lead_model_context
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.platform.config import get_settings
from pathfinder.tests._support.database import detached_session

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


@pytest.fixture
def _cloud_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_tier", "quality", raising=False)


@pytest.fixture
def no_quota_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _accumulate(
        session: AsyncSession,
        *,
        user_id: Any,
        tokens: int,
        cost_usd: Decimal,
        paid_by: PaidBy,
    ) -> None:
        del session, user_id, tokens, cost_usd, paid_by

    monkeypatch.setattr(quota, "accumulate", _accumulate)


@pytest.mark.usefixtures("_cloud_provider")
def test_the_tier_effort_comes_back_beside_the_model() -> None:
    resolved = resolve_lead_model_context(build_lead_agent())

    assert (resolved.model_id, resolved.reasoning_effort) == (
        "openai:gpt-5.6-sol",
        "high",
    )


@pytest.mark.usefixtures("_cloud_provider")
def test_a_request_effort_wins_over_the_tier() -> None:
    resolved = resolve_lead_model_context(build_lead_agent(), reasoning_effort="low")

    assert resolved.reasoning_effort == "low"


def test_the_mock_provider_states_no_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(), "pathfinder_chat_provider", "mock", raising=False
    )

    resolved = resolve_lead_model_context(build_lead_agent())

    assert (resolved.model_id, resolved.reasoning_effort) == ("mock:lead", None)


def test_the_usage_chunk_carries_the_effort() -> None:
    collector = _Collector()
    capture = _LeadRunCapture()
    capture.lead_model = _LEAD_MODEL
    capture.lead_reasoning_effort = "high"

    emit_lead_usage(collector, capture, 12, "0.01")

    assert collector.lead_usage[0]["reasoningEffort"] == "high"


def test_the_usage_chunk_states_no_effort_when_the_run_has_none() -> None:
    collector = _Collector()
    capture = _LeadRunCapture()
    capture.lead_model = _LEAD_MODEL

    emit_lead_usage(collector, capture, 0, "0")

    payload = collector.lead_usage[0]
    assert (payload["modelId"], payload["reasoningEffort"]) == (_LEAD_MODEL, None)


@pytest.mark.asyncio
async def test_the_live_chunk_reads_the_effort_off_the_capture(
    no_quota_writes: None,
) -> None:
    capture = _LeadRunCapture()
    capture.lead_model = _LEAD_MODEL
    capture.lead_reasoning_effort = "high"
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find kinases.",
    )
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=detached_session,
        cancel_event=asyncio.Event(),
    )
    collector = _Collector()

    await _charge_token_delta(
        context,
        state,
        capture,
        RunUsage(input_tokens=1200, output_tokens=20),
        collector,
        _LEAD_MODEL,
    )

    assert collector.lead_usage[0]["reasoningEffort"] == "high"
