"""A typed reply is written after the facts part the turn shows beside it, and a
turn whose facts hold nothing writes no facts part."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from langgraph.runtime import Runtime

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.conversation._turn_helpers import _extract_chunk
from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import stop_response
from pathfinder.ai.graph.lead_node import _run_lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database

_REPLY = "I saved the genes; the set is shown beside this reply."


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Save these genes as a set named kinases draft.",
    )


def _runtime() -> Runtime[Context]:
    return Runtime(
        context=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        )
    )


async def _turn(
    monkeypatch: pytest.MonkeyPatch, *, saved: bool
) -> tuple[list[dict[str, Any]], PipelineState]:
    payloads: list[object] = []

    async def _answered(
        *, deps: LeadDeps, capture: _LeadRunCapture, **_kwargs: Any
    ) -> None:
        if saved:
            deps.state.turn_markers.record_gene_set(
                CreatedGeneSet(id="gs-1", name="kinases draft", gene_count=61)
            )
        capture.response = stop_response(_REPLY, changed=False)

    async def _pre_turn(state: PipelineState, _context: Context) -> PipelineState:
        return state

    async def _nothing(*_args: Any) -> list[object]:
        return []

    monkeypatch.setattr(lead_node, "get_stream_writer", lambda: payloads.append)
    monkeypatch.setattr(lead_node, "retrieve_memories", _nothing)
    monkeypatch.setattr(lead_node, "_drive_lead_stream", _answered)
    state = _state()
    command = await _run_lead_turn(
        state, _runtime(), pre_turn=_pre_turn, build_agent=build_lead_agent
    )
    assert isinstance(command.update, dict)
    after = state.model_copy(update={"domain": command.update["domain"]})
    chunks = [chunk for p in payloads if (chunk := _extract_chunk(p)) is not None]
    return chunks, after


async def test_the_facts_part_comes_before_the_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written, _ = await _turn(monkeypatch, saved=True)
    types = [str(chunk["type"]) for chunk in written]
    (facts,) = [chunk["data"] for chunk in written if chunk["type"] == "data-facts"]

    assert types.index("data-facts") < types.index("text-start")
    assert facts["saved"] == [
        {"kind": "gene_set", "name": "kinases draft", "count": 61}
    ]


async def test_a_turn_whose_facts_hold_nothing_writes_no_facts_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written, _ = await _turn(monkeypatch, saved=False)

    assert "data-facts" not in [chunk["type"] for chunk in written]
    assert [chunk["delta"] for chunk in written if chunk["type"] == "text-delta"] == [
        _REPLY
    ]


async def test_the_facts_a_turn_shows_are_kept_for_the_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, after = await _turn(monkeypatch, saved=True)

    assert after.domain.facts_shown == ["Saved gene set kinases draft, 61 genes"]
