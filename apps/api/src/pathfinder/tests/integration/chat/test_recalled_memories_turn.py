"""A turn recalls the researcher's preferences into one part, one row per
memory; a case or a strategy waits until the Lead recalls it."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select

from pathfinder.domain.memory import standing_memory_key
from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_plasmodb,
    suite_search,
)
from pathfinder.tests.integration.chat._helpers import run_one_chat_turn

_GOAL = (
    "Find P. falciparum 3D7 genes with a signal peptide and at least 2 "
    "transmembrane domains"
)
_EARLIER = datetime(2026, 9, 13, 16, 44, tzinfo=UTC)
_LATER = datetime(2026, 9, 16, 12, 23, tzinfo=UTC)


@pytest.fixture(autouse=True)
def recorded_plasmodb(monkeypatch: pytest.MonkeyPatch) -> None:
    """The goal builds one GenesByTaxon step, read from its recording."""
    serve_recorded_plasmodb(monkeypatch, [suite_search("search_genes_by_taxon")])


def _case(*, count: int, created_at: datetime, source: UUID) -> MemoryValue:
    return MemoryValue(
        kind="case",
        name=_GOAL,
        summary=f"{_GOAL} reached {count} results",
        site_id="plasmodb",
        content={"case": "outcome", "goal": _GOAL, "root_count": count},
        source_conversation_id=source,
        created_at=created_at,
    )


def _strategy(source: UUID) -> MemoryValue:
    return MemoryValue(
        kind="strategy",
        name=f"chat-{source.hex[:8]}",
        summary="signal peptide and transmembrane domains",
        site_id="plasmodb",
        content={"user_prompt": _GOAL},
        source_conversation_id=source,
        created_at=_LATER,
    )


async def _recalled_rows() -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        chunks = (
            await session.scalars(
                select(ConversationEvent.chunk).order_by(ConversationEvent.id),
            )
        ).all()
    return [c for c in chunks if c["type"] == "data-memory-retrieved"]


def _preference(name: str, summary: str) -> MemoryValue:
    return MemoryValue(
        kind="preference",
        name=name,
        summary=summary,
        content={"preference": summary},
        created_at=_EARLIER,
    )


@pytest.fixture
async def seeded(
    app_memory_store: MemoryStore,
    authed_user_id: UUID,
) -> dict[str, UUID]:
    """Two preferences, two cases for one goal from two threads, and the
    strategy of one."""
    store = MemoryStore(
        store=app_memory_store.store,
        application_id=PATHFINDER_APPLICATION_ID,
    )
    first, second = uuid4(), uuid4()
    for name, summary in (
        ("Default organism", "Plasmodium falciparum 3D7"),
        ("SignalP version", "SignalP-6.0"),
    ):
        await store.put(
            user_id=authed_user_id,
            value=_preference(name, summary),
            key=standing_memory_key(name),
        )
    await store.put(
        user_id=authed_user_id,
        value=_case(count=3, created_at=_EARLIER, source=first),
        key="case:earlier",
    )
    await store.put(
        user_id=authed_user_id,
        value=_case(count=18, created_at=_LATER, source=second),
        key="case:later",
    )
    await store.put(
        user_id=authed_user_id,
        value=_strategy(second),
        key=f"strategy:{second.hex}",
    )
    return {"first": first, "second": second}


async def test_one_turn_writes_one_recalled_part_with_one_row_per_memory(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
    seeded: dict[str, UUID],
) -> None:
    del signed_in_to_veupathdb
    await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_GOAL,
    )

    parts = await _recalled_rows()
    assert len(parts) == 1
    keys = Counter(m["key"] for m in parts[0]["data"]["memories"])
    assert keys == Counter(
        [
            standing_memory_key("Default organism"),
            standing_memory_key("SignalP version"),
        ],
    )
