from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.revision import answer_revision
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.services.gene_sets.step_genes import TooManyGenesError
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.strategies.auto_import import (
    import_gene_set_for_conversation,
)
from pathfinder.tests._support.gene_set_refresh import (
    RootAnswer,
    run_refresh_job,
    serve_roots,
    store_root,
)

pytestmark = pytest.mark.usefixtures("worker_seams")

_WDK_STRATEGY = 214_645_070
_NARROWED = [f"PF3D7_{n:07d}" for n in range(39)]
_ABOVE = RootAnswer(refusal=TooManyGenesError(523_795, 10_000))


async def _thread(
    session_maker: async_sessionmaker[AsyncSession], *, deleted_its_set: bool
) -> tuple[UUID, UUID]:
    async with session_maker() as session:
        user = User(id=uuid4())
        session.add(user)
        await session.commit()
        repo = ConversationRepository(session)
        created = await repo.create(
            user.id, "plasmodb", assistant_id="pathfinder", name="Singletons"
        )
        await repo.update_conversation(
            created.id,
            ConversationUpdate(
                wdk_strategy_id=_WDK_STRATEGY,
                wdk_strategy_id_set=True,
                gene_set_auto_imported=deleted_its_set,
            ),
        )
        await session.commit()
    return created.id, user.id


@pytest.fixture
async def unsaved_thread(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    patch_app_db_engine: None,
) -> tuple[UUID, UUID]:
    del db_cleaner, patch_app_db_engine
    return await _thread(session_maker, deleted_its_set=False)


async def _linked(conversation_id: UUID) -> tuple[str | None, bool]:
    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    return strategy.gene_set_id, strategy.gene_set_auto_imported


async def test_a_write_within_the_cap_imports_the_new_root(
    unsaved_thread: tuple[UUID, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    thread, user_id = unsaved_thread
    serve_roots(monkeypatch, [RootAnswer(_NARROWED)])
    stored = await store_root(thread, CombineOp.INTERSECT)

    await run_refresh_job(thread)

    [imported] = await GeneSetStore().list_for_user(user_id)
    assert (imported.name, imported.gene_ids, imported.answer_revision) == (
        "Singletons",
        _NARROWED,
        answer_revision(stored),
    )
    assert await _linked(thread) == (imported.id, True)


async def test_a_write_still_above_the_cap_links_nothing(
    unsaved_thread: tuple[UUID, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    thread, user_id = unsaved_thread
    serve_roots(monkeypatch, [_ABOVE])
    await store_root(thread, CombineOp.UNION)

    await run_refresh_job(thread)

    assert (await GeneSetStore().list_for_user(user_id), await _linked(thread)) == (
        [],
        (None, False),
    )


async def test_a_thread_whose_set_was_deleted_imports_nothing(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    patch_app_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_cleaner, patch_app_db_engine
    thread, user_id = await _thread(session_maker, deleted_its_set=True)
    served = serve_roots(monkeypatch, [RootAnswer(_NARROWED)])
    await store_root(thread, CombineOp.INTERSECT)

    await run_refresh_job(thread)

    assert (served.tokens, await GeneSetStore().list_for_user(user_id)) == ([], [])


async def test_two_imports_at_once_save_one_set(
    unsaved_thread: tuple[UUID, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    thread, user_id = unsaved_thread
    served = serve_roots(monkeypatch, [RootAnswer(_NARROWED), RootAnswer(_NARROWED)])
    await store_root(thread, CombineOp.INTERSECT)

    await asyncio.gather(
        *(
            import_gene_set_for_conversation(
                conversation_id=thread,
                site_id="plasmodb",
                user_id=user_id,
                name="Strategy result",
            )
            for _ in range(2)
        )
    )

    listed = await GeneSetStore().list_for_user(user_id)
    assert ([gs.gene_ids for gs in listed], len(served.tokens)) == ([_NARROWED], 1)
    assert await _linked(thread) == (listed[0].id, True)
