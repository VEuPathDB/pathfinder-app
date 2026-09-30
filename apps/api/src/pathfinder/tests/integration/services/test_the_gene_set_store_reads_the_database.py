"""Every gene set store reads the row another process wrote last."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet

_SET = "gs-shared-1"


@pytest.fixture
async def seed_user(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    patch_app_db_engine: None,
) -> User:
    del db_cleaner, patch_app_db_engine
    user = User(id=uuid4())
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    return user


def _set(user_id: UUID) -> GeneSet:
    return GeneSet(
        id=_SET,
        name="Kinases",
        site_id="plasmodb",
        gene_ids=["PF3D7_1133400", "PF3D7_0709000"],
        source="strategy",
        user_id=user_id,
    )


async def test_a_store_reads_the_genes_another_store_wrote(seed_user: User) -> None:
    """Two processes hold two stores; each read returns the last write."""
    api, worker = GeneSetStore(), GeneSetStore()
    await api.save(_set(seed_user.id))
    assert await api.get(_SET) is not None

    refreshed = await worker.get(_SET)
    assert refreshed is not None
    refreshed.gene_ids = ["PF3D7_1222600"]
    await worker.save(refreshed)

    read = await api.get(_SET)
    assert read is not None
    assert read.gene_ids == ["PF3D7_1222600"]


async def test_a_rename_leaves_the_genes_another_store_wrote(seed_user: User) -> None:
    """A rename from a copy read before a refresh keeps the refreshed genes."""
    api, worker = GeneSetStore(), GeneSetStore()
    await api.save(_set(seed_user.id))
    stale = await api.get(_SET)
    assert stale is not None

    refreshed = await worker.get(_SET)
    assert refreshed is not None
    refreshed.gene_ids = ["PF3D7_1222600"]
    await worker.save(refreshed)
    await GeneSetService(api).rename(stale, "Kinases of the root")

    read = await worker.get(_SET)
    assert read is not None
    assert (read.name, read.gene_ids) == ("Kinases of the root", ["PF3D7_1222600"])


async def test_a_delete_in_one_store_is_gone_from_the_other(seed_user: User) -> None:
    api, worker = GeneSetStore(), GeneSetStore()
    await api.save(_set(seed_user.id))
    assert await worker.get(_SET) is not None

    assert await worker.delete(_SET) is True

    assert await api.get(_SET) is None
    assert await api.list_for_user(seed_user.id) == []
    assert await api.delete(_SET) is False


async def test_the_import_is_found_by_a_store_that_did_not_write_it(
    seed_user: User, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """A set saved in a thread or pasted on the strategy is never the import."""
    async with session_maker() as session:
        conversation = await ConversationRepository(session).create(
            seed_user.id, "plasmodb", assistant_id="pathfinder"
        )
        await session.commit()
    api, worker = GeneSetStore(), GeneSetStore()
    on_the_strategy = replace(_set(seed_user.id), wdk_strategy_id=404)
    await worker.save(
        replace(on_the_strategy, id="gs-in-thread", conversation_id=conversation.id)
    )
    await worker.save(replace(on_the_strategy, id="gs-pasted", source="paste"))
    before = await api.find_strategy_import(seed_user.id, 404)
    await worker.save(on_the_strategy)

    after = await api.find_strategy_import(seed_user.id, 404)

    assert before is None
    assert after is not None
    assert (after.id, after.wdk_strategy_id) == (_SET, 404)


async def test_a_list_is_newest_first_and_narrowed_by_site(seed_user: User) -> None:
    store = GeneSetStore()
    older = replace(
        _set(seed_user.id), id="gs-old", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    newer = replace(
        _set(seed_user.id), id="gs-new", created_at=datetime(2026, 2, 1, tzinfo=UTC)
    )
    elsewhere = replace(_set(seed_user.id), id="gs-toxo", site_id="toxodb")
    for gene_set in (older, newer, elsewhere):
        await store.save(gene_set)

    listed = await GeneSetStore().list_for_user(seed_user.id, site_id="plasmodb")

    assert [gs.id for gs in listed] == ["gs-new", "gs-old"]
    assert [gs.id for gs in await GeneSetStore().list_all(site_id="toxodb")] == [
        "gs-toxo"
    ]
