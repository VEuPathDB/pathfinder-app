"""A fresh turn shows a recalled memory once per conversation, and hands back
how many memories of each kind the Lead can recall."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import StoredMemory
from langgraph.runtime import Runtime

from pathfinder.ai.conversation._turn_helpers import _extract_chunk
from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _run_lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database

_PREFERENCE = StoredMemory(
    key="default-organism",
    value=MemoryValue(
        kind="preference",
        name="Default organism",
        summary="Plasmodium falciparum 3D7",
        content={},
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    ),
)
_INDEX = {"strategy": 4, "case": 2}


async def _turn(
    monkeypatch: pytest.MonkeyPatch, domain: StrategyDomainState
) -> tuple[list[dict[str, Any]], StrategyDomainState]:
    payloads: list[object] = []

    async def _answered(
        *, deps: LeadDeps, capture: _LeadRunCapture, **_kwargs: Any
    ) -> None:
        del deps
        capture.response = LeadResponse(prose="Done.", strategy_changed=False)

    async def _pre_turn(state: PipelineState, _context: Context) -> PipelineState:
        return state

    async def _recalled(*_args: Any) -> list[StoredMemory]:
        return [_PREFERENCE]

    async def _indexed(*_args: Any) -> dict[str, int]:
        return dict(_INDEX)

    monkeypatch.setattr(lead_node, "get_stream_writer", lambda: payloads.append)
    monkeypatch.setattr(lead_node, "retrieve_memories", _recalled)
    monkeypatch.setattr(lead_node, "memory_index", _indexed)
    monkeypatch.setattr(lead_node, "_drive_lead_stream", _answered)
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find secreted kinases.",
        domain=domain,
    )
    runtime = Runtime(
        context=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        )
    )
    handed_back = await _run_lead_turn(
        state, runtime, pre_turn=_pre_turn, build_agent=build_lead_agent
    )
    match handed_back.update:
        case {"domain": StrategyDomainState() as after}:
            pass
        case other:
            pytest.fail(f"the turn handed back no domain: {other!r}")
    written = [c for p in payloads if (c := _extract_chunk(p)) is not None]
    return written, after


def _cards(written: list[dict[str, Any]]) -> list[list[str]]:
    return [
        [m["name"] for m in chunk["data"]["memories"]]
        for chunk in written
        if chunk["type"] == "data-memory-retrieved"
    ]


async def test_a_memory_shows_on_the_first_turn_that_recalls_it_and_not_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, after_first = await _turn(monkeypatch, StrategyDomainState())
    second, _ = await _turn(monkeypatch, after_first)

    assert (_cards(first), _cards(second)) == ([["Default organism"]], [])


async def test_the_turn_hands_back_what_the_lead_can_recall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, after = await _turn(monkeypatch, StrategyDomainState())

    assert after.memory_index == _INDEX
