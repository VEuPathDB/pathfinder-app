"""A memory store the conformance client can reach.

The schemathesis ASGI transport drives the application on a blocking portal of
its own (``schemathesis/python/asgi.py::_get_portal``), so a store whose
futures belong to the loop that opened it cannot serve those requests. This one
holds its rows in a dict and belongs to no loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import StoredMemory

from pathfinder.domain.memory import MemoryKind

__all__ = ["LoopFreeMemoryStore", "seed_key", "seeded_memory"]

_SEED_CONVERSATION_ID = UUID("00000000-0000-4000-8000-00000000c0de")


def seed_key(kind: MemoryKind) -> str:
    """The key the seeded memory of a kind is stored under."""
    return f"seed-{kind}"


def seeded_memory(kind: MemoryKind) -> MemoryValue:
    """One memory of a kind, with every optional field set."""
    return MemoryValue(
        kind=kind,
        name=f"a {kind} the conformance run reads",
        summary=f"one {kind} memory",
        tags=[kind],
        site_id="plasmodb",
        content={"kind": kind, "count": 1},
        auto_retrieve=True,
        source_conversation_id=_SEED_CONVERSATION_ID,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_used_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


@dataclass
class LoopFreeMemoryStore:
    """The surface the memories router and the purge call, backed by a dict."""

    rows: dict[tuple[UUID, str, str], MemoryValue] = field(default_factory=dict)

    def _of_kind(self, user_id: UUID, kind: str) -> list[StoredMemory]:
        return [
            StoredMemory(key=key, value=value)
            for (row_user, row_kind, key), value in self.rows.items()
            if row_user == user_id and row_kind == kind
        ]

    async def put(
        self,
        *,
        user_id: UUID,
        value: MemoryValue,
        key: str | None = None,
    ) -> str:
        mem_key = key or str(uuid4())
        self.rows[(user_id, value.kind, mem_key)] = value
        return mem_key

    async def get(
        self,
        *,
        user_id: UUID,
        kind: str,
        key: str,
    ) -> StoredMemory | None:
        row = (user_id, kind, key)
        if row not in self.rows:
            return None
        return StoredMemory(key=key, value=self.rows[row])

    async def delete(self, *, user_id: UUID, kind: str, key: str) -> None:
        row = (user_id, kind, key)
        if row in self.rows:
            del self.rows[row]

    async def list_all(
        self,
        *,
        user_id: UUID,
        kind: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StoredMemory]:
        return self._of_kind(user_id, kind)[offset : offset + limit]

    async def semantic_search(
        self,
        *,
        user_id: UUID,
        kind: str,
        query: str,
        top_k: int = 8,
    ) -> list[StoredMemory]:
        del query
        return self._of_kind(user_id, kind)[:top_k]
