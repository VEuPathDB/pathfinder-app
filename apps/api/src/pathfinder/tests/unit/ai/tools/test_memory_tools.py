"""What ``remember`` writes: one row per standing preference, many per case."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from langgraph.store.base import Item
from langgraph.store.postgres.aio import AsyncPostgresStore
from pydantic_ai import ModelRetry, RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.memory_tools import remember
from pathfinder.domain.memory import MemoryKind
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


class _RecordingStore(AsyncPostgresStore):
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


async def _remember(ctx: RunContext[AgentDeps], kind: MemoryKind, content: str) -> str:
    return returned(
        await remember(
            ctx,
            kind=kind,
            name="Default organism",
            summary="the organism a turn assumes",
            content={"organism": content},
        ),
        str,
    )


def _one_user(store: _RecordingStore) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    ctx.deps.memory_store = store
    return ctx


async def test_a_second_preference_of_one_name_replaces_the_first() -> None:
    store = _RecordingStore()
    ctx = _one_user(store)

    first = await _remember(ctx, "preference", "P. falciparum 3D7")
    second = await _remember(ctx, "preference", "Plasmodium berghei ANKA")

    assert len(store.rows) == 1
    (payload,) = store.rows.values()
    assert payload["content"] == {"organism": "Plasmodium berghei ANKA"}
    assert first.startswith("Stored")
    assert second.startswith("Updated")


async def test_two_cases_of_one_name_are_both_kept() -> None:
    store = _RecordingStore()
    ctx = _one_user(store)

    await _remember(ctx, "case", "P. falciparum 3D7")
    await _remember(ctx, "case", "Plasmodium berghei ANKA")

    assert len(store.rows) == 2


async def test_a_preference_with_no_name_is_sent_back_to_the_model() -> None:
    """A key derived from nothing would be one bucket for every such name."""
    ctx = _one_user(_RecordingStore())

    with pytest.raises(ModelRetry, match="name"):
        await remember(
            ctx,
            kind="preference",
            name="???",
            summary="the organism a turn assumes",
            content={"organism": "Plasmodium berghei ANKA"},
        )
