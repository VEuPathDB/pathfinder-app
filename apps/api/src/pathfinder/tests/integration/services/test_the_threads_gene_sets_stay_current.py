"""The gene sets a thread lists are current and name the thread they came from.

The refresh job puts the set auto-import made on the root each commit stores,
and a set saved in the thread still names the thread after a reload.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.wdk import GeneSetWdkContext

from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.services.evidence.gene_sets import list_stored_gene_sets
from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.store import GeneSetStore, get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies.auto_import import (
    import_gene_set_for_conversation,
)
from pathfinder.tests._support.gene_set_refresh import run_refresh_job, store_root

_WDK_STRATEGY = 330_642_473
_AUTO_SET = "gs-follows-the-strategy"
_SAVED_SET = "gs-saved-in-the-thread"
# The root's genes after the first build and after each of two commits.
_BUILT = [f"PF3D7_{n:07d}" for n in range(549)]
_FIRST_COMMIT = _BUILT[:39]
_SECOND_COMMIT = _BUILT[:288]


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def thread(db_session: AsyncSession, patch_app_db_engine: None) -> UUID:
    """A built thread whose auto-imported set holds the first build's root."""
    del patch_app_db_engine
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.commit()
    store = get_gene_set_store()
    repo = ConversationRepository(db_session)
    created = await repo.create(
        user.id, "plasmodb", assistant_id="pathfinder", name="Vaccine antigens"
    )
    await db_session.commit()
    for gene_set in (
        GeneSet(
            id=_AUTO_SET,
            name="Vaccine antigens",
            site_id="plasmodb",
            gene_ids=list(_BUILT),
            source="strategy",
            user_id=user.id,
            wdk_strategy_id=_WDK_STRATEGY,
            record_type="transcript",
        ),
        GeneSet(
            id=_SAVED_SET,
            name="vaccine candidates draft",
            site_id="plasmodb",
            gene_ids=list(_FIRST_COMMIT),
            source="strategy",
            user_id=user.id,
            conversation_id=created.id,
        ),
    ):
        await store.save(gene_set)
    await repo.update_conversation(
        created.id,
        ConversationUpdate(
            wdk_strategy_id=_WDK_STRATEGY,
            wdk_strategy_id_set=True,
            gene_set_id=_AUTO_SET,
            gene_set_id_set=True,
            gene_set_auto_imported=True,
        ),
    )
    await db_session.commit()
    return created.id


def _serve_roots(monkeypatch: pytest.MonkeyPatch, roots: list[list[str]]) -> None:
    """Each read of the strategy's root answers the next result in ``roots``."""

    async def _resolve(
        site_id: str, gene_ids: list[str], ctx: GeneSetWdkContext
    ) -> tuple[list[str], GeneSetWdkContext, int]:
        del site_id, gene_ids
        return roots.pop(0), ctx, 3

    monkeypatch.setattr(operations, "resolve_wdk_context", _resolve)


async def test_after_two_commits_the_set_holds_the_current_root(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_roots(monkeypatch, [list(_FIRST_COMMIT), list(_SECOND_COMMIT)])

    await store_root(thread, CombineOp.UNION)
    await run_refresh_job(thread)
    await store_root(thread, CombineOp.INTERSECT)
    await run_refresh_job(thread)

    reloaded = await GeneSetStore().get(_AUTO_SET)
    assert reloaded is not None
    assert len(reloaded.gene_ids) == 288
    assert reloaded.gene_ids == _SECOND_COMMIT


async def test_a_set_saved_in_the_thread_names_it_after_a_reload(
    thread: UUID,
) -> None:
    reloaded = await GeneSetStore().get(_SAVED_SET)

    assert reloaded is not None
    assert (reloaded.name, len(reloaded.gene_ids), reloaded.conversation_id) == (
        "vaccine candidates draft",
        39,
        thread,
    )
    listed = await list_stored_gene_sets(site_id="plasmodb", user_id=reloaded.user_id)
    assert {gs.id: gs.conversation_id for gs in listed} == {
        _AUTO_SET: None,
        _SAVED_SET: thread,
    }


async def test_a_set_the_user_linked_is_never_refreshed(
    thread: UUID, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await ConversationRepository(db_session).update_conversation(
        thread, ConversationUpdate(gene_set_auto_imported=False)
    )
    await db_session.commit()
    _serve_roots(monkeypatch, [list(_SECOND_COMMIT)])

    await store_root(thread, CombineOp.INTERSECT)
    await run_refresh_job(thread)

    reloaded = await GeneSetStore().get(_AUTO_SET)
    assert reloaded is not None
    assert len(reloaded.gene_ids) == 549


async def test_a_build_beside_a_saved_set_imports_its_own_and_leaves_the_saved_one(
    db_session: AsyncSession,
    patch_app_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A set saved from a step before the first import is never linked or refreshed."""
    del patch_app_db_engine
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.commit()
    repo = ConversationRepository(db_session)
    created = await repo.create(
        user.id, "plasmodb", assistant_id="pathfinder", name="Vaccine antigens"
    )
    await db_session.commit()
    await get_gene_set_store().save(
        GeneSet(
            id=_SAVED_SET,
            name="vaccine candidates draft",
            site_id="plasmodb",
            gene_ids=list(_FIRST_COMMIT),
            source="strategy",
            user_id=user.id,
            wdk_strategy_id=_WDK_STRATEGY,
            wdk_step_id=439_858_733,
            record_type="transcript",
            conversation_id=created.id,
        )
    )
    await repo.update_conversation(
        created.id,
        ConversationUpdate(wdk_strategy_id=_WDK_STRATEGY, wdk_strategy_id_set=True),
    )
    await db_session.commit()
    _serve_roots(monkeypatch, [list(_BUILT), list(_FIRST_COMMIT), list(_SECOND_COMMIT)])

    imported = await import_gene_set_for_conversation(
        conversation_id=created.id,
        site_id="plasmodb",
        user_id=user.id,
        name="Strategy result",
    )
    await store_root(created.id, CombineOp.UNION)
    await run_refresh_job(created.id)
    await store_root(created.id, CombineOp.INTERSECT)
    await run_refresh_job(created.id)

    assert imported is not None
    assert imported.id != _SAVED_SET
    async with async_session_factory() as session:
        linked = await ConversationRepository(session).get_strategy(created.id)
    assert (linked.gene_set_id, linked.gene_set_auto_imported) == (imported.id, True)
    own = await GeneSetStore().get(imported.id)
    saved = await GeneSetStore().get(_SAVED_SET)
    assert own is not None
    assert saved is not None
    assert (own.name, own.gene_ids) == ("Vaccine antigens", _SECOND_COMMIT)
    assert (saved.name, saved.gene_ids, saved.wdk_step_id) == (
        "vaccine candidates draft",
        _FIRST_COMMIT,
        439_858_733,
    )
