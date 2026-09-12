"""What the turn recalls is written to the thread in the envelope the runner reads.

The turn runner keeps a payload only when it is the ``{"chunk": {...}}``
envelope, so an emission of any other shape never reaches an event row.
"""

from __future__ import annotations

import ast
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import StoredMemory
from langgraph.runtime import Runtime

from pathfinder.ai import graph, lead
from pathfinder.ai.conversation._turn_helpers import _extract_chunk
from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph.lead_node import _run_lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database

_MEMORY_KEY = "case:signal-peptide-and-transmembrane"


def _stored_memory() -> StoredMemory:
    return StoredMemory(
        key=_MEMORY_KEY,
        value=MemoryValue(
            kind="case",
            name="signal peptide and transmembrane",
            summary="the intersection reached 195 genes",
            content={"count": 195},
            created_at=datetime.now(UTC),
        ),
        score=0.853,
    )


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="find genes with a signal peptide and a transmembrane domain",
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


@pytest.fixture
async def written(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The chunks the runner keeps from one turn that recalled one memory."""
    payloads: list[object] = []

    async def _no_lead_run(**_kwargs: Any) -> None:
        return None

    async def _one_memory(*_args: Any) -> list[StoredMemory]:
        return [_stored_memory()]

    async def _pre_turn(state: PipelineState, _context: Context) -> PipelineState:
        return state

    monkeypatch.setattr(lead_node, "get_stream_writer", lambda: payloads.append)
    monkeypatch.setattr(lead_node, "retrieve_memories", _one_memory)
    monkeypatch.setattr(lead_node, "_drive_lead_stream", _no_lead_run)
    await _run_lead_turn(
        _state(),
        _runtime(),
        pre_turn=_pre_turn,
        build_agent=build_lead_agent,
    )
    return [chunk for p in payloads if (chunk := _extract_chunk(p)) is not None]


async def test_the_runner_keeps_the_recalled_memories_chunk(
    written: list[dict[str, Any]],
) -> None:
    recalled = [c for c in written if c["type"] == "data-memory-retrieved"]

    assert len(recalled) == 1


async def test_the_kept_chunk_names_the_memory_the_turn_recalled(
    written: list[dict[str, Any]],
) -> None:
    (recalled,) = [c for c in written if c["type"] == "data-memory-retrieved"]

    assert [m["key"] for m in recalled["data"]["memories"]] == [_MEMORY_KEY]


def _bare_writer_calls(package: ModuleType) -> list[str]:
    """Every call that hands the stream writer something the runner cannot read."""
    root = Path(str(package.__file__)).parent
    return [
        f"{path.relative_to(root.parent)}:{node.lineno}"
        for path in sorted(root.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "writer"
    ]


def test_the_graph_writes_only_the_envelope() -> None:
    assert _bare_writer_calls(graph) == []


def test_the_lead_writes_only_the_envelope() -> None:
    assert _bare_writer_calls(lead) == []


def test_the_guard_walks_every_module_of_the_graph_and_the_lead() -> None:
    """A walk that finds no file would pass the two rules above."""
    walked = {
        path.name
        for package in (graph, lead)
        for path in Path(str(package.__file__)).parent.rglob("*.py")
    }

    assert {"lead_node.py", "pre_turn.py", "edit_dispatch.py"} <= walked
