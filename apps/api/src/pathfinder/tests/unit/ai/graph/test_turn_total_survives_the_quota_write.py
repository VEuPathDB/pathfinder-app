"""What a served search cost stays in the turn total after the quota is written.

The usage event the user reads, the amount the monthly quota receives and the
number the checkpoint keeps are one accounting; a thread that drops the tool
charge from the checkpoint restarts the next turn from a smaller total.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from assistant_core import quota
from assistant_core.platform.db import DBSessionFactory
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph._lead_capture import (
    SpendOutsideTheLead,
    _LeadRunCapture,
    _persist_residual_quota,
    absorb_tool_charge,
)
from pathfinder.ai.graph._lead_delta import _build_state_delta
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, ToolCharge
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import detached_session

_CHARGE = Decimal("0.005")
_LEAD_COST = Decimal("1.100")
_SUB_AGENT_COST = Decimal("0.020")
_SUB_AGENT_TOKENS = 500
_TURN_COST = Decimal("1.125")


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        domain=StrategyDomainState(),
    )


class _CommitRefusingSession(AsyncSession):
    """A session the database refuses to commit."""

    async def commit(self) -> None:
        statement = "commit"
        raise OperationalError(statement, {}, Exception("connection lost"))


def _commit_refusing_session() -> AsyncSession:
    return _CommitRefusingSession()


def _deps(
    state: PipelineState,
    session_factory: DBSessionFactory = detached_session,
) -> LeadDeps:
    return LeadDeps(
        state=state,
        intent=None,
        runtime=Context(
            site_id="plasmodb",
            user_id=state.user_id,
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=session_factory,
            cancel_event=asyncio.Event(),
        ),
        retrieved_memories=[],
    )


def _charged_capture() -> _LeadRunCapture:
    """A turn whose Lead calls are already billed, with a pass and a paid search."""
    capture = _LeadRunCapture()
    capture.tokens = 10
    capture.cost_usd = _LEAD_COST
    capture.charged_input_tokens = 10
    capture.charged_cost = _LEAD_COST
    capture.sub_agent_tokens = _SUB_AGENT_TOKENS
    capture.sub_agent_cost = _SUB_AGENT_COST
    absorb_tool_charge(
        capture, ToolCharge(tool_name="research_web_search", cost_usd=_CHARGE)
    )
    return capture


def _recording_quota(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, Decimal]]:
    billed: list[tuple[int, Decimal]] = []

    async def accumulate(
        session: AsyncSession,
        *,
        user_id: UUID | None,
        tokens: int,
        cost_usd: Decimal,
    ) -> None:
        del session, user_id
        billed.append((tokens, cost_usd))

    monkeypatch.setattr(quota, "accumulate", accumulate)
    return billed


async def test_the_usage_event_the_quota_and_the_checkpoint_agree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()
    deps = _deps(state)
    capture = _charged_capture()
    billed = _recording_quota(monkeypatch)

    shown_tokens, shown = capture.residual_totals(state)
    await _persist_residual_quota(deps.runtime, state, capture)
    delta = _build_state_delta(state=state, deps=deps, capture=capture, memories=[])

    assert (shown_tokens, shown) == (510, "1.125")
    assert billed == [(_SUB_AGENT_TOKENS, _SUB_AGENT_COST + _CHARGE)]
    assert delta["turn_total_cost_usd"] == _TURN_COST
    assert delta["turn_total_tokens"] == 510


async def test_a_refused_quota_write_bills_nothing_and_keeps_the_turn_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused write advances no marker and does not end the turn.

    The monthly quota never receives the spend. The usage event and the
    checkpoint still carry it, so the next turn starts from the true total.
    """
    state = _state()
    deps = _deps(state)
    capture = _charged_capture()
    attempted: list[tuple[int, Decimal]] = []

    async def refuse(
        session: AsyncSession,
        *,
        user_id: UUID | None,
        tokens: int,
        cost_usd: Decimal,
    ) -> None:
        del session, user_id
        attempted.append((tokens, cost_usd))
        statement = "insert into usage_quota"
        raise OperationalError(statement, {}, Exception("no connection"))

    monkeypatch.setattr(quota, "accumulate", refuse)

    await _persist_residual_quota(deps.runtime, state, capture)
    delta = _build_state_delta(state=state, deps=deps, capture=capture, memories=[])

    assert attempted == [(_SUB_AGENT_TOKENS, _SUB_AGENT_COST + _CHARGE)]
    assert capture.billed_outside_the_lead == SpendOutsideTheLead()
    assert capture.charged_cost == _LEAD_COST
    assert capture.tool_cost == _CHARGE
    assert capture.residual_totals(state) == (510, "1.125")
    assert delta["turn_total_cost_usd"] == _TURN_COST
    assert delta["turn_total_tokens"] == 510


async def test_a_commit_the_database_refuses_ends_the_write_and_not_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spend the commit did not store is unbilled, and the turn goes on.

    The turn emits its usage event, its ledger and its state delta after this
    write, so an exception here would lose all three.
    """
    state = _state()
    deps = _deps(state, _commit_refusing_session)
    capture = _charged_capture()
    attempted = _recording_quota(monkeypatch)

    await _persist_residual_quota(deps.runtime, state, capture)
    delta = _build_state_delta(state=state, deps=deps, capture=capture, memories=[])

    assert attempted == [(_SUB_AGENT_TOKENS, _SUB_AGENT_COST + _CHARGE)]
    assert capture.billed_outside_the_lead == SpendOutsideTheLead()
    assert capture.charged_cost == _LEAD_COST
    assert delta["turn_total_cost_usd"] == _TURN_COST
    assert delta["turn_total_tokens"] == 510


async def test_one_search_is_billed_to_the_quota_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()
    deps = _deps(state)
    capture = _charged_capture()
    billed = _recording_quota(monkeypatch)

    await _persist_residual_quota(deps.runtime, state, capture)
    await _persist_residual_quota(deps.runtime, state, capture)

    assert billed == [(_SUB_AGENT_TOKENS, _SUB_AGENT_COST + _CHARGE)]
    assert capture.spend_outside_the_lead() == capture.billed_outside_the_lead
