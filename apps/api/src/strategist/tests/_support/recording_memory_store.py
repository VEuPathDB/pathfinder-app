"""A memory store that keeps one payload per namespace and key in a dict."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langgraph.store.base import Item
from langgraph.store.postgres.aio import AsyncPostgresStore


class RecordingMemoryStore(AsyncPostgresStore):
    """Keeps one payload per namespace and key, as the real store does."""

    def __init__(self) -> None:
        self.rows: dict[tuple[tuple[str, ...], str], dict[str, Any]] = {}
        self._task = None

    async def aput(self, *args: Any, **kwargs: Any) -> None:
        namespace, key, payload = args[0], args[1], args[2]
        del kwargs
        self.rows[(tuple(namespace), key)] = payload

    async def aget(self, *args: Any, **kwargs: Any) -> Item | None:
        del kwargs
        namespace, key = tuple(args[0]), args[1]
        payload = self.rows.get((namespace, key))
        if payload is None:
            return None
        return Item(
            value=payload,
            key=key,
            namespace=namespace,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
