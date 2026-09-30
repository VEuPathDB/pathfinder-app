"""A memory-store call that never answers ends, and the turn keeps its reply."""

from __future__ import annotations

import asyncio
from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.platform.config import RuntimeSettings, use_settings_source
from langgraph.runtime import Runtime
from langgraph.store.postgres.aio import AsyncPostgresStore

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph import _lead_turn, nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.logs import logged_events


class _StoreThatNeverAnswers(AsyncPostgresStore):
    """Stands in for the LangGraph store with a batch task that never resolves."""

    def __init__(self) -> None:
        """The store holds no connection and no batch task: every call waits."""
        self._task = None

    async def asearch(self, *args: Any, **kwargs: Any) -> list[Any]:
        del args, kwargs
        await asyncio.Event().wait()
        raise AssertionError

    async def aput(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        await asyncio.Event().wait()


class _NoTombstones:
    """A tombstone repository the auto-write can consult without a database."""

    def __init__(self, *, session_factory: Any) -> None:
        del session_factory

    async def existing_hashes(
        self,
        *,
        user_id: UUID,
        values: Sequence[MemoryValue],
    ) -> set[tuple[str, str]]:
        del user_id, values
        return set()


def _context(store: AsyncPostgresStore | None = None) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
        memory_store=store or _StoreThatNeverAnswers(),
    )


def _state(*, verified: bool = False) -> PipelineState:
    domain = StrategyDomainState()
    if verified:
        domain = StrategyDomainState(
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="ok",
                reason="verified",
                success=True,
            ),
        )
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="which kinases are essential",
        domain=domain,
    )
    state.turn_markers.verification_dispatched = verified
    return state


@pytest.fixture
def short_deadline() -> Generator[None]:
    use_settings_source(lambda: RuntimeSettings(memory_store_timeout_seconds=0.05))
    yield
    use_settings_source(RuntimeSettings)


async def test_retrieval_degrades_to_no_memories(
    short_deadline: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A store that never answers costs the turn its memories, not the turn."""
    del short_deadline
    runtime: Runtime[Context] = Runtime(context=_context())

    found = await _lead_turn.retrieve_memories(_state(), runtime)

    assert found == []
    assert logged_events(caplog.records) == [
        "memory retrieval timed out; the turn runs without memories"
    ]


async def test_retrieval_gives_up_at_the_deadline(short_deadline: None) -> None:
    """Retrieval costs the turn the window, not the whole turn."""
    del short_deadline
    loop = asyncio.get_running_loop()
    started = loop.time()
    runtime: Runtime[Context] = Runtime(context=_context())

    await _lead_turn.retrieve_memories(_state(), runtime)
    elapsed = loop.time() - started

    assert 0.05 <= elapsed < 1.0


def _candidate() -> MemoryValue:
    return MemoryValue(
        kind="knowledge",
        name="kinome",
        summary="the kinome has 105 members",
        content={"count": 105},
        created_at=datetime.now(UTC),
    )


def _finalize_without_io(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_turn_message(**kwargs: Any) -> None:
        del kwargs

    async def _one_candidate(
        _state: PipelineState,
        **_kwargs: object,
    ) -> Sequence[tuple[MemoryValue, str]]:
        return [(_candidate(), "kinome")]

    async def _no_compaction(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(nodes, "write_turn_message", _no_turn_message)
    monkeypatch.setattr(nodes, "collect_turn_memory_candidates", _one_candidate)
    monkeypatch.setattr(nodes, "TombstoneRepository", _NoTombstones)
    monkeypatch.setattr(nodes, "compact_scratchpad", _no_compaction)


async def test_an_auto_write_timeout_leaves_the_turn_finished(
    short_deadline: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A store that never answers the auto-write costs the notes, not the reply."""
    del short_deadline
    _finalize_without_io(monkeypatch)
    runtime: Runtime[Context] = Runtime(context=_context())

    command = await nodes.finalize_turn_node(_state(verified=True), runtime)

    assert command.goto == "__end__"
    assert command.update is None
    assert logged_events(caplog.records, logger=nodes.__name__) == [
        "the memory auto-write failed; the turn keeps its reply"
    ]


class _EmbeddingRefusedError(Exception):
    """An embedding client error that subclasses none of the builtin I/O errors."""


class _StoreWhoseEmbeddingFails(_StoreThatNeverAnswers):
    """Stands in for a store whose embedding call raises inside ``aput``."""

    async def aput(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise _EmbeddingRefusedError


async def test_an_auto_write_that_raises_keeps_the_gene_sets_to_note(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Any auto-write failure after the reply ends the turn normally, notes unwritten."""
    _finalize_without_io(monkeypatch)
    runtime: Runtime[Context] = Runtime(context=_context(_StoreWhoseEmbeddingFails()))
    state = _state(verified=True)
    saved = CreatedGeneSet(id="gs-1", name="Pf kinases", gene_count=105)
    state.domain.created_gene_sets.append(saved)

    command = await nodes.finalize_turn_node(state, runtime)

    assert command.goto == "__end__"
    assert command.update is None
    assert state.domain.created_gene_sets == [saved]
    assert logged_events(caplog.records, logger=nodes.__name__) == [
        "the memory auto-write failed; the turn keeps its reply"
    ]
