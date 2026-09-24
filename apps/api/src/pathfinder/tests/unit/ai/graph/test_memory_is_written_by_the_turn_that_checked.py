"""The memory auto-write and the compaction run only in the turn that ran the check."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from langgraph.runtime import Runtime
from langgraph.store.postgres.aio import AsyncPostgresStore

from pathfinder.ai.graph import nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database


class _RecordingStore(AsyncPostgresStore):
    """A store the node can hold without a connection."""

    def __init__(self) -> None:
        self._task = None


class _NoTombstones:
    def __init__(self, *, session_factory: Any) -> None:
        del session_factory

    async def existing_hashes(
        self, *, user_id: UUID, values: Sequence[MemoryValue]
    ) -> set[tuple[str, str]]:
        del user_id, values
        return set()


def _verified_state(
    *, checked_this_turn: bool, pending: tuple[str, ...] = ()
) -> PipelineState:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="what does PF3D7_1133400 do",
        domain=StrategyDomainState(
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="ok",
                reason="verified",
                success=True,
                pending_checks=list(pending),
            )
        ),
    )
    state.turn_markers.verified = checked_this_turn
    state.turn_markers.verification_dispatched = checked_this_turn
    return state


async def _finalize(
    monkeypatch: pytest.MonkeyPatch, state: PipelineState
) -> tuple[int, int]:
    """Run the finalize node; answer (memory writes, compaction runs)."""
    compactions = 0

    async def _no_turn_message(**kwargs: Any) -> None:
        del kwargs

    async def _one_candidate(_: PipelineState) -> Sequence[tuple[MemoryValue, str]]:
        return [
            (
                MemoryValue(
                    kind="knowledge",
                    name="kinome",
                    summary="the kinome has 105 members",
                    content={"count": 105},
                    created_at=datetime.now(UTC),
                ),
                "kinome",
            )
        ]

    async def _count_compaction(**kwargs: Any) -> None:
        nonlocal compactions
        del kwargs
        compactions += 1

    writes = 0

    async def _count_write(**kwargs: Any) -> None:
        nonlocal writes
        del kwargs
        writes += 1

    store = _RecordingStore()
    monkeypatch.setattr(nodes, "write_turn_message", _no_turn_message)
    monkeypatch.setattr(nodes, "collect_turn_memory_candidates", _one_candidate)
    monkeypatch.setattr(nodes, "TombstoneRepository", _NoTombstones)
    monkeypatch.setattr(nodes, "auto_write_memories", _count_write)
    monkeypatch.setattr(nodes, "compact_scratchpad", _count_compaction)
    runtime: Runtime[Context] = Runtime(
        context=Context(
            site_id="plasmodb",
            user_id=state.user_id,
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
            memory_store=store,
        )
    )
    await nodes.finalize_turn_node(state, runtime)
    return writes, compactions


async def test_a_turn_that_ran_no_check_writes_no_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A standing verdict from an earlier turn is not this turn's finding."""
    written = await _finalize(monkeypatch, _verified_state(checked_this_turn=False))

    assert written == (0, 0)


async def test_the_turn_that_checked_writes_its_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = await _finalize(monkeypatch, _verified_state(checked_this_turn=True))

    assert written == (1, 1)


async def test_a_check_with_a_pending_step_writes_no_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A finding whose study step nobody could check is not written as one; the
    turn that checked still compacts its notes."""
    written = await _finalize(
        monkeypatch, _verified_state(checked_this_turn=True, pending=("step_de",))
    )

    assert written == (0, 1)
