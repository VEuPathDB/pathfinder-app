from __future__ import annotations

import asyncio

from assistant_core.memory.deadline import (
    MemoryStoreTimeoutError,
    memory_store_deadline,
)
from assistant_core.memory.retrieval import RetrievalScope, retrieve_relevant_memories
from assistant_core.memory.store import MemoryStore, StoredMemory
from assistant_core.platform.logging import get_logger
from langgraph.runtime import Runtime

from strategist.ai.graph.runtime import Context
from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.domain.memory import MEMORY_KINDS, STANDING_MEMORY_KINDS, MemoryKind
from strategist.domain.unread import Unread

logger = get_logger(__name__)


# The memories of one kind the index reads; the index says only how many there are.
_INDEXED_PER_KIND = 100


def _turn_scope(site_id: str) -> RetrievalScope:
    """The memories a turn of this site reads: the standing kinds whole, and no
    other kind ranked, since the Lead recalls those with search_memory."""
    return RetrievalScope(
        kinds=(),
        always_kinds=STANDING_MEMORY_KINDS,
        keep=lambda memory: memory.site_id in (None, site_id),
    )


_STORE_DOWN = Unread(reason="the memory store did not answer")
MEMORY_NOT_READ = (
    f"Your saved preferences were not read this turn ({_STORE_DOWN.reason})."
)
MEMORY_NOT_COUNTED = (
    f"Your other saved memories were not counted this turn ({_STORE_DOWN.reason}); "
    "search_memory still reads them."
)


def recalled(
    read: list[StoredMemory] | Unread, domain: StrategyDomainState
) -> list[StoredMemory]:
    """The memories a turn pins; preferences the store did not answer are named
    in the turn briefing instead."""
    match read:
        case Unread():
            domain.turn_briefing = "\n\n".join(
                block for block in (domain.turn_briefing, MEMORY_NOT_READ) if block
            )
            return []
        case stored:
            return stored


async def retrieve_memories(
    state: PipelineState,
    runtime: Runtime[Context],
) -> list[StoredMemory] | Unread:
    """The standing memories a fresh turn pins, the researcher's preferences, or
    why the store did not give them."""
    if runtime.context is None or runtime.context.memory_store is None:
        return []
    if not state.user_prompt.strip():
        return []
    mem_store = MemoryStore(store=runtime.context.memory_store)
    try:
        async with memory_store_deadline("memory retrieval"):
            return await retrieve_relevant_memories(
                store=mem_store,
                user_id=state.user_id,
                query=state.user_prompt,
                scope=_turn_scope(state.site_id),
            )
    except MemoryStoreTimeoutError as exc:
        logger.warning(
            "memory retrieval timed out; the turn runs without memories",
            seconds=exc.seconds,
        )
        return _STORE_DOWN


def indexed(
    read: dict[MemoryKind, int] | Unread, domain: StrategyDomainState
) -> dict[MemoryKind, int]:
    match read:
        case Unread():
            domain.turn_briefing = "\n\n".join(
                block for block in (domain.turn_briefing, MEMORY_NOT_COUNTED) if block
            )
            return {}
        case counted:
            return counted


async def memory_index(
    state: PipelineState,
    runtime: Runtime[Context],
) -> dict[MemoryKind, int] | Unread:
    """How many memories of each kind but the standing ones the Lead can recall
    on this site, a kind with none left out."""
    if runtime.context is None or runtime.context.memory_store is None:
        return {}
    mem_store = MemoryStore(store=runtime.context.memory_store)
    scope = _turn_scope(state.site_id)
    kinds: list[MemoryKind] = [
        k for k in MEMORY_KINDS if k not in STANDING_MEMORY_KINDS
    ]
    try:
        async with memory_store_deadline("memory index"):
            listed = await asyncio.gather(
                *(
                    mem_store.list_all(
                        user_id=state.user_id, kind=k, limit=_INDEXED_PER_KIND
                    )
                    for k in kinds
                )
            )
    except MemoryStoreTimeoutError as exc:
        logger.warning("memory index timed out", seconds=exc.seconds)
        return _STORE_DOWN
    counts: dict[MemoryKind, int] = {
        kind: sum(1 for stored in found if scope.admits(stored.value))
        for kind, found in zip(kinds, listed, strict=True)
    }
    return {kind: n for kind, n in counts.items() if n}
