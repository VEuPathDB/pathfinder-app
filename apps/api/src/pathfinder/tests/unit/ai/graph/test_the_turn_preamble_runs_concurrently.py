"""The turn preamble: recall and the thread read are one step, run together."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import StoredMemory
from langgraph.runtime import Runtime

from pathfinder.ai.conversation._turn_helpers import _extract_chunk
from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph.lead_node import _run_lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.graph.turn_status import (
    READING_THE_THREAD,
    RECALLING_AND_READING,
)
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database

_MEET_SECONDS = 2.0
_WORKING_PROMPT = "the state the thread read returned"


def _memory_value(name: str) -> MemoryValue:
    return MemoryValue(
        kind="case",
        name=name,
        summary="the intersection reached 195 genes",
        content={"count": 195},
        created_at=datetime(2026, 9, 18, tzinfo=UTC),
    )


_RECALLED = StoredMemory(
    key="case:recalled", value=_memory_value("recalled"), score=0.9
)


def _state(**overrides: Any) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="find genes with a signal peptide",
        **overrides,
    )


def _parked_state() -> PipelineState:
    return _state(
        pending_approval=PendingApproval(
            phase="lead",
            tool_call_id="call-1",
            tool_name="consult_user",
        ),
        retrieved_memories=[_memory_value("already on the state")],
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


class _ThreadReadError(RuntimeError):
    """What the thread read raises in the failure test below."""


class _Preamble:
    """Stand-ins for both halves of the preamble, and what they recorded."""

    def __init__(
        self, *, rendezvous: bool, read_error: Exception | None = None
    ) -> None:
        self.rendezvous = rendezvous
        self.read_error = read_error
        self.barrier = asyncio.Barrier(2)
        self.order: list[str] = []
        self.payloads: list[object] = []
        self.deps: LeadDeps | None = None
        self.retrievals = 0

    async def _half(self, name: str) -> None:
        self.order.append(f"{name}:start")
        if self.rendezvous:
            async with asyncio.timeout(_MEET_SECONDS):
                await self.barrier.wait()
        self.order.append(f"{name}:end")

    async def retrieve(self, *_args: Any) -> list[StoredMemory]:
        self.retrievals += 1
        await self._half("recall")
        return [_RECALLED]

    async def pre_turn(self, state: PipelineState, _context: Context) -> PipelineState:
        await self._half("read")
        if self.read_error is not None:
            raise self.read_error
        return state.model_copy(update={"user_prompt": _WORKING_PROMPT})

    @property
    def labels(self) -> list[str]:
        return [
            chunk["data"]["label"]
            for payload in self.payloads
            if (chunk := _extract_chunk(payload)) is not None
            and chunk["type"] == "data-turn-status"
        ]

    @property
    def kinds(self) -> list[str]:
        return [
            chunk["type"]
            for payload in self.payloads
            if (chunk := _extract_chunk(payload)) is not None
        ]

    def lead_deps(self) -> LeadDeps:
        assert self.deps is not None
        return self.deps


async def _drive(
    preamble: _Preamble,
    state: PipelineState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _capture_deps(**kwargs: Any) -> None:
        preamble.deps = kwargs["deps"]

    monkeypatch.setattr(
        lead_node, "get_stream_writer", lambda: preamble.payloads.append
    )
    monkeypatch.setattr(lead_node, "retrieve_memories", preamble.retrieve)
    monkeypatch.setattr(lead_node, "_drive_lead_stream", _capture_deps)
    await _run_lead_turn(
        state,
        _runtime(),
        pre_turn=preamble.pre_turn,
        build_agent=build_lead_agent,
    )


async def test_both_halves_of_the_preamble_are_in_flight_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preamble = _Preamble(rendezvous=True)

    await _drive(preamble, _state(), monkeypatch)

    order = preamble.order
    assert order.index("read:start") < order.index("recall:end")
    assert order.index("recall:start") < order.index("read:end")


async def test_a_fresh_turn_reports_one_step_that_names_both_halves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preamble = _Preamble(rendezvous=True)

    await _drive(preamble, _state(), monkeypatch)

    assert preamble.labels == [RECALLING_AND_READING]


async def test_the_lead_reads_the_recalled_memories_and_the_working_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preamble = _Preamble(rendezvous=True)

    await _drive(preamble, _state(), monkeypatch)

    deps = preamble.lead_deps()
    assert deps.retrieved_memories == [_RECALLED.value]
    assert deps.state.user_prompt == _WORKING_PROMPT


async def test_the_fresh_turn_writes_the_memory_it_recalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preamble = _Preamble(rendezvous=True)

    await _drive(preamble, _state(), monkeypatch)

    assert preamble.kinds.count("data-memory-retrieved") == 1


async def test_a_thread_read_that_raises_ends_the_turn_and_recalls_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed thread read ends the turn before any memory chunk is written."""
    preamble = _Preamble(rendezvous=True, read_error=_ThreadReadError())

    with pytest.raises(_ThreadReadError):
        await _drive(preamble, _state(), monkeypatch)

    assert preamble.retrievals == 1
    assert "data-memory-retrieved" not in preamble.kinds


async def test_a_turn_that_resumes_a_parked_call_recalls_nothing_and_still_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preamble = _Preamble(rendezvous=False)

    await _drive(preamble, _parked_state(), monkeypatch)

    assert preamble.retrievals == 0
    assert preamble.order == ["read:start", "read:end"]
    assert preamble.lead_deps().state.user_prompt == _WORKING_PROMPT


async def test_a_parked_turn_reports_only_the_thread_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preamble = _Preamble(rendezvous=False)

    await _drive(preamble, _parked_state(), monkeypatch)

    assert preamble.labels == [READING_THE_THREAD]


async def test_a_parked_turn_hands_the_lead_the_memories_the_state_carries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preamble = _Preamble(rendezvous=False)
    state = _parked_state()

    await _drive(preamble, state, monkeypatch)

    assert preamble.lead_deps().retrieved_memories == state.retrieved_memories
