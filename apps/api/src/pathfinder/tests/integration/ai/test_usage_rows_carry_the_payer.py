"""Every token lands in the monthly ledger, on the row of whoever paid for it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from assistant_core import quota
from assistant_core.cost import cost_for_run
from assistant_core.persistence.models import MonthlyUsage
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import PaidBy
from pydantic import SecretStr
from pydantic_ai.usage import RunUsage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.graph._lead_capture import (
    _charge_token_delta,
    _LeadRunCapture,
    _persist_residual_quota,
    absorb_sub_agent_usage,
    absorb_tool_charge,
)
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import SubAgentRunUsage, ToolCharge
from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import User
from pathfinder.platform.model_keys import attach_keyring
from pathfinder.tests.integration.http.conftest import make_user

_TOOL_CHARGE = Decimal("0.005")
_KEYRING = ProviderKeyring(
    active={"anthropic": SecretStr("sk-ant-sentinel-0123456789WXYZ")}
)
_DEFAULT_LIMIT = Decimal(20)


@pytest.fixture
async def user(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    patch_app_db_engine: None,
) -> AsyncGenerator[User]:
    del db_cleaner, patch_app_db_engine
    async with session_maker() as session:
        yield await make_user(session)


def _state(user: User) -> PipelineState:
    return PipelineState(
        conversation_id=user.id,
        user_id=user.id,
        site_id="plasmodb",
        mode="strategy",
        domain=StrategyDomainState(),
    )


def _context(user: User) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=user.id,
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=async_session_factory,
        cancel_event=asyncio.Event(),
    )


async def _rows(user: User) -> dict[PaidBy, tuple[int, Decimal]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(MonthlyUsage).where(MonthlyUsage.user_id == user.id)
        )
        return {
            row.paid_by: (row.total_tokens, row.total_cost_usd)
            for row in result.scalars()
        }


def _pass(model_id: str, paid_by: PaidBy, tokens: int) -> SubAgentRunUsage:
    provider, _, model = model_id.partition(":")
    return SubAgentRunUsage(
        usage=RunUsage(input_tokens=tokens, output_tokens=0),
        model_name=model,
        provider_name=provider,
        provider_url=None,
        parent_tool_call_id=f"call-{model}",
        paid_by=paid_by,
    )


def _cost(model_id: str, tokens: int) -> Decimal:
    provider, _, model = model_id.partition(":")
    return cost_for_run(
        usage=RunUsage(input_tokens=tokens, output_tokens=0),
        model_name=model,
        provider_name=provider,
        provider_url=None,
    )


async def test_a_streamed_charge_on_the_researchers_key_is_theirs(user: User) -> None:
    capture = _LeadRunCapture()
    lead = "anthropic:claude-opus-5"
    usage = RunUsage(input_tokens=1000, output_tokens=200)

    written: list[object] = []

    with attach_keyring(_KEYRING):
        await _charge_token_delta(
            _context(user),
            _state(user),
            capture,
            usage,
            writer=written.append,
            agent_model=lead,
        )

    rows = await _rows(user)
    assert list(rows) == [PaidBy.USER]
    assert rows[PaidBy.USER][0] == 1200
    async with async_session_factory() as session:
        status = await quota.get_current(session, user.id, limit_usd=_DEFAULT_LIMIT)
    assert (status.used_usd, status.total_tokens) == (Decimal(0), 0)


async def test_the_residual_splits_by_payer_and_the_tool_charge_is_the_deployments(
    user: User,
) -> None:
    lead = "anthropic:claude-opus-5"
    keyed_pass = _pass("anthropic:claude-sonnet-5", PaidBy.USER, 400)
    deployment_pass = _pass("openai:gpt-5.6-luna", PaidBy.DEPLOYMENT, 700)
    capture = _LeadRunCapture(lead_model=lead, tokens=300, cost_usd=Decimal("0.3"))
    absorb_sub_agent_usage(capture, keyed_pass)
    absorb_sub_agent_usage(capture, deployment_pass)
    absorb_tool_charge(capture, ToolCharge(tool_name="research", cost_usd=_TOOL_CHARGE))

    with attach_keyring(_KEYRING):
        await _persist_residual_quota(_context(user), _state(user), capture)

    rows = await _rows(user)
    own_cost = Decimal("0.3") + _cost("anthropic:claude-sonnet-5", 400)
    deployment_cost = _cost("openai:gpt-5.6-luna", 700) + _TOOL_CHARGE
    assert rows == {
        PaidBy.USER: (700, own_cost.quantize(Decimal("0.000001"))),
        PaidBy.DEPLOYMENT: (700, deployment_cost.quantize(Decimal("0.000001"))),
    }
    async with async_session_factory() as session:
        status = await quota.get_current(session, user.id, limit_usd=_DEFAULT_LIMIT)
        own = await quota.get_period_totals(session, user.id, paid_by=PaidBy.USER)
    assert status.used_usd == rows[PaidBy.DEPLOYMENT][1]
    assert (own.cost_usd, own.tokens) == (rows[PaidBy.USER][1], 700)
