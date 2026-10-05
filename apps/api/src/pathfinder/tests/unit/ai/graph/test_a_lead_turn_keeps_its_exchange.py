"""A Lead turn writes its exchange into the conversation it hands back, after
the exchanges earlier turns kept."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from langgraph.runtime import Runtime

from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _run_lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.exchanges import Exchange
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database

_EARLIER = Exchange(said="Show me a sample of five genes.", reply="Five genes: ...")
_ASKED = "Can you show me that same sample of five genes again?"
_REPLY = "Here are the same five genes."


async def test_the_turn_hands_back_its_exchange_after_the_earlier_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _answered(
        *, deps: LeadDeps, capture: _LeadRunCapture, **_kwargs: Any
    ) -> None:
        del deps
        capture.response = LeadResponse(prose=_REPLY, strategy_changed=False)

    async def _pre_turn(state: PipelineState, _context: Context) -> PipelineState:
        return state

    async def _nothing(*_args: Any) -> list[object]:
        return []

    monkeypatch.setattr(lead_node, "get_stream_writer", lambda: lambda _chunk: None)
    monkeypatch.setattr(lead_node, "retrieve_memories", _nothing)
    monkeypatch.setattr(lead_node, "_drive_lead_stream", _answered)
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="hostdb",
        mode="strategy",
        user_prompt=_ASKED,
        domain=StrategyDomainState(exchanges=[_EARLIER]),
    )
    runtime = Runtime(
        context=Context(
            site_id="hostdb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="hostdb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        )
    )

    handed_back = await _run_lead_turn(
        state, runtime, pre_turn=_pre_turn, build_agent=build_lead_agent
    )

    match handed_back.update:
        case {"domain": StrategyDomainState() as domain}:
            assert domain.exchanges == [_EARLIER, Exchange(said=_ASKED, reply=_REPLY)]
        case other:
            pytest.fail(f"the turn handed back no domain: {other!r}")
