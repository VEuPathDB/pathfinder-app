"""A fresh turn reads the VEuPathDB pages its message links to before its agent runs."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.memory.store import StoredMemory
from langgraph.runtime import Runtime
from pydantic_ai import RunContext
from veupathdb_mcp.records import LinkReading

from pathfinder.ai.explore import explore_agent
from pathfinder.ai.graph import explore_node, lead_node
from pathfinder.ai.graph._lead_capture import LeadRunCapture
from pathfinder.ai.graph.lead_node import _run_lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    explore_state,
    install_explore_doubles,
    run_explore,
)

GENOMES = (
    "https://qa.veupathdb.org/veupathdb.qa/app/search/organism/GenomeDataTypes/result"
)
READING = LinkReading(
    url=GENOMES,
    site_id="veupathdb",
    kind="search_result",
    summary="The link runs GenomeDataTypes on veupathdb.",
)


@pytest.fixture
def read(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    async def linked(prompt: str) -> list[LinkReading]:
        asked.append(prompt)
        return [READING] if GENOMES in prompt else []

    monkeypatch.setattr(lead_node, "read_linked_pages", linked)
    monkeypatch.setattr(explore_node, "read_linked_pages", linked)
    return asked


async def _lead_turn(monkeypatch: pytest.MonkeyPatch, prompt: str) -> LeadDeps:
    held: list[LeadDeps] = []

    async def answered(*, deps: LeadDeps, capture: LeadRunCapture, **_: Any) -> None:
        held.append(deps)
        capture.response = LeadResponse(prose="Done.")

    async def pre_turn(state: PipelineState, _context: Context) -> PipelineState:
        return state

    async def recalled(*_args: Any) -> list[StoredMemory]:
        return []

    async def indexed(*_args: Any) -> dict[str, int]:
        return {}

    monkeypatch.setattr(lead_node, "get_stream_writer", lambda: lambda _p: None)
    monkeypatch.setattr(lead_node, "retrieve_memories", recalled)
    monkeypatch.setattr(lead_node, "memory_index", indexed)
    monkeypatch.setattr(lead_node, "_drive_lead_stream", answered)
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="veupathdb",
        mode="build",
        user_prompt=prompt,
    )
    runtime = Runtime(
        context=Context(
            site_id="veupathdb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="veupathdb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        )
    )
    await _run_lead_turn(
        state, runtime, pre_turn=pre_turn, build_agent=build_lead_agent
    )
    return held[0]


async def test_a_lead_turn_holds_the_reading_of_its_link(
    monkeypatch: pytest.MonkeyPatch, read: list[str]
) -> None:
    deps = await _lead_turn(monkeypatch, f"can you read this web page {GENOMES}")

    assert read == [f"can you read this web page {GENOMES}"]
    assert deps.linked_pages == [READING]


async def test_an_explore_turn_holds_the_reading_of_its_link(
    monkeypatch: pytest.MonkeyPatch, read: list[str]
) -> None:
    install_explore_doubles(monkeypatch)
    pinned: list[list[LinkReading]] = []

    def spy(ctx: RunContext[LeadDeps]) -> str | None:
        pinned.append(list(ctx.deps.linked_pages))
        return None

    monkeypatch.setattr(explore_agent, "pinned_linked_pages", spy)
    prompt = f"{EXPLORE_PROMPT} {GENOMES}"

    await run_explore(explore_state(prompt))

    assert read == [prompt]
    assert pinned[0] == [READING]
