"""The local half of the purge: what a DELETE /user/data call destroys here."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.persistence.models import Conversation, MemoryTombstoneRow
from assistant_core.platform.db import async_session_factory
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import EvalStagedCase, GeneSetRow, User
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.tests.integration.http._user_data_purge import (
    OTHER_SITE,
    SITE,
    add_conv,
    add_staged_case,
    api_client,
    db_session,
    other_application_client,
    seed_user,
)

__all__ = ["api_client", "db_session", "other_application_client", "seed_user"]


async def test_purge_dismisses_all_conversations_and_reports_counts(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    no_wdk = await add_conv(
        db_session,
        seed_user.id,
        site_id="plasmodb",
        wdk_strategy_id=None,
        created_here=False,
    )
    wdk_linked = await add_conv(
        db_session,
        seed_user.id,
        site_id="plasmodb",
        wdk_strategy_id=555,
        created_here=True,
    )

    resp = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": "plasmodb"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "ok": True,
        "deleted": {
            "strategies": 2,
            "wdkStrategies": 0,
            "wdkStrategiesKept": 0,
            "memories": 0,
            "geneSets": 0,
            "experiments": 0,
            "controlSets": 0,
            "stagedEvalCases": 0,
        },
    }

    async with session_maker() as verify:
        rows = (
            (
                await verify.execute(
                    select(Conversation).where(Conversation.user_id == seed_user.id)
                )
            )
            .scalars()
            .all()
        )
    by_id = {c.id: c for c in rows}
    assert set(by_id) == {no_wdk, wdk_linked}
    assert by_id[no_wdk].dismissed_at is not None
    assert by_id[wdk_linked].dismissed_at is not None


async def test_a_purge_from_another_application_destroys_nothing(
    api_client: httpx.AsyncClient,
    other_application_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A caller destroys only what it can see."""
    conversation = await add_conv(
        db_session,
        seed_user.id,
        site_id="plasmodb",
        wdk_strategy_id=None,
        created_here=False,
    )
    gene_set = await GeneSetService(get_gene_set_store()).create(
        user_id=seed_user.id,
        name="kinases",
        site_id="plasmodb",
        gene_ids=["PF3D7_0100100"],
        source="paste",
    )

    resp = await other_application_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": "plasmodb"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "ok": True,
        "deleted": {
            "strategies": 0,
            "wdkStrategies": 0,
            "wdkStrategiesKept": 0,
            "memories": 0,
            "geneSets": 0,
            "experiments": 0,
            "controlSets": 0,
            "stagedEvalCases": 0,
        },
    }
    async with session_maker() as verify:
        survivor = await verify.get(Conversation, conversation)
        gene_set_row = await verify.get(GeneSetRow, gene_set.id)
    assert survivor is not None
    assert survivor.dismissed_at is None
    assert gene_set_row is not None
    assert gene_set.id in get_gene_set_store()._cache

    owner = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": "plasmodb"}
    )

    assert owner.json()["deleted"] == {
        "strategies": 1,
        "wdkStrategies": 0,
        "wdkStrategiesKept": 0,
        "memories": 0,
        "geneSets": 1,
        "experiments": 0,
        "controlSets": 0,
        "stagedEvalCases": 0,
    }
    async with session_maker() as verify:
        purged = await verify.get(Conversation, conversation)
        assert purged is not None
        assert purged.dismissed_at is not None
        assert await verify.get(GeneSetRow, gene_set.id) is None
    assert gene_set.id not in get_gene_set_store()._cache


async def test_purge_respects_site_scope(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    here = await add_conv(
        db_session,
        seed_user.id,
        site_id="plasmodb",
        wdk_strategy_id=None,
        created_here=False,
    )
    elsewhere = await add_conv(
        db_session,
        seed_user.id,
        site_id="toxodb",
        wdk_strategy_id=None,
        created_here=False,
    )

    resp = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": "plasmodb"}
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"]["strategies"] == 1

    async with session_maker() as verify:
        rows = {
            c.id: c
            for c in (
                await verify.execute(
                    select(Conversation).where(Conversation.user_id == seed_user.id)
                )
            )
            .scalars()
            .all()
        }
    assert rows[here].dismissed_at is not None
    assert rows[elsewhere].dismissed_at is None


def _memory(name: str, kind: str) -> MemoryValue:
    return MemoryValue(
        kind=kind,
        name=name,
        summary=name,
        tags=[],
        content={"note": name},
        created_at=datetime.now(UTC),
    )


async def _seed_memories(store: MemoryStore, user: User) -> None:
    await store.put(user_id=user.id, value=_memory("a fact", "knowledge"))
    await store.put(user_id=user.id, value=_memory("a habit", "preference"))
    await TombstoneRepository(session_factory=async_session_factory).tombstone(
        user_id=user.id,
        value=_memory("a deleted note", "gene_set_note"),
    )


async def _memory_counts(
    store: MemoryStore,
    user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[int, int]:
    """How many memories the user still holds, and how many tombstones."""
    held = 0
    for kind in ("knowledge", "preference"):
        held += len(await store.list_all(user_id=user.id, kind=kind))
    async with session_maker() as verify:
        tombstones = await verify.scalar(
            select(func.count())
            .select_from(MemoryTombstoneRow)
            .where(MemoryTombstoneRow.user_id == user.id),
        )
    return held, tombstones or 0


async def test_clearing_all_data_deletes_the_memories_and_their_tombstones(
    api_client: httpx.AsyncClient,
    app_memory_store: MemoryStore,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_memories(app_memory_store, seed_user)

    resp = await api_client.request("DELETE", "/api/v1/user/data")

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["memories"] == 2
    assert await _memory_counts(app_memory_store, seed_user, session_maker) == (0, 0)


async def test_clearing_one_site_leaves_the_memories_alone(
    api_client: httpx.AsyncClient,
    app_memory_store: MemoryStore,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A memory names no site, so a site purge is not the one that clears it."""
    await _seed_memories(app_memory_store, seed_user)

    resp = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": SITE}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["memories"] == 0
    assert await _memory_counts(app_memory_store, seed_user, session_maker) == (2, 1)


async def _staged_sites(
    session_maker: async_sessionmaker[AsyncSession],
    user: User,
) -> list[str]:
    async with session_maker() as verify:
        rows = await verify.scalars(
            select(EvalStagedCase.site_id).where(EvalStagedCase.user_id == user.id),
        )
    return sorted(rows)


async def test_a_site_purge_deletes_only_that_site_s_staged_eval_cases(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A staged case names a site, so a site purge reaches only its own."""
    here = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=None,
        created_here=False,
    )
    elsewhere = await add_conv(
        db_session,
        seed_user.id,
        site_id=OTHER_SITE,
        wdk_strategy_id=None,
        created_here=False,
    )
    await add_staged_case(db_session, seed_user.id, site_id=SITE, conversation_id=here)
    await add_staged_case(
        db_session, seed_user.id, site_id=OTHER_SITE, conversation_id=elsewhere
    )

    resp = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": SITE}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["stagedEvalCases"] == 1
    assert await _staged_sites(session_maker, seed_user) == [OTHER_SITE]


async def test_a_purge_leaves_another_application_s_staged_eval_cases(
    other_application_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A caller destroys only what it can read."""
    mine = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=None,
        created_here=False,
    )
    await add_staged_case(db_session, seed_user.id, site_id=SITE, conversation_id=mine)

    resp = await other_application_client.request("DELETE", "/api/v1/user/data")

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["stagedEvalCases"] == 0
    assert await _staged_sites(session_maker, seed_user) == [SITE]
