from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.memory.store import StoredMemory
from assistant_core.platform.types import PaidBy
from langgraph.runtime import Runtime

from strategist.ai.graph import lead_node
from strategist.ai.graph._lead_capture import LeadRunCapture, absorb_outside_spend
from strategist.ai.graph.lead_node import _run_lead_turn
from strategist.ai.graph.runtime import Context
from strategist.ai.graph.state import PipelineState
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.domain.strategy.session import StrategySession
from strategist.tests._support.database import no_database

_READER_TOKENS = 600


async def test_a_build_turn_the_researcher_stops_charges_the_readers_spend_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    charged: list[int] = []

    async def read_then_stopped(*, capture: LeadRunCapture, **_: Any) -> None:
        absorb_outside_spend(capture, _READER_TOKENS, Decimal("0.001"), PaidBy.USER)
        raise asyncio.CancelledError

    async def charge(
        context: Context | None, state: PipelineState, capture: LeadRunCapture
    ) -> None:
        del context, state
        charged.append(capture.sub_agent_tokens)

    async def pre_turn(state: PipelineState, _context: Context) -> PipelineState:
        return state

    async def recalled(*_args: Any) -> list[StoredMemory]:
        return []

    async def indexed(*_args: Any) -> dict[str, int]:
        return {}

    async def no_pages(prompt: str) -> list[object]:
        del prompt
        return []

    monkeypatch.setattr(lead_node, "get_stream_writer", lambda: lambda _p: None)
    monkeypatch.setattr(lead_node, "retrieve_memories", recalled)
    monkeypatch.setattr(lead_node, "memory_index", indexed)
    monkeypatch.setattr(lead_node, "read_linked_pages", no_pages)
    monkeypatch.setattr(lead_node, "_drive_lead_stream", read_then_stopped)
    monkeypatch.setattr(lead_node, "_persist_residual_quota", charge)
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="build",
        user_prompt="kinases on chromosome 12",
    )
    runtime = Runtime(
        context=Context(
            site_id="plasmodb",
            user_id=state.user_id,
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        )
    )

    with pytest.raises(asyncio.CancelledError):
        await _run_lead_turn(
            state, runtime, pre_turn=pre_turn, build_agent=build_lead_agent
        )

    assert charged == [_READER_TOKENS]
