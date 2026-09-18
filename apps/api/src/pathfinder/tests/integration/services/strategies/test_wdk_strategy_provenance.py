"""The strategy row records who made the WDK strategy it names.

A purge deletes on VEuPathDB only what PathFinder minted there, so the flag
is written by the sync that minted it and by nothing else.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import application_id_ctx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree, WDKStrategyDetails

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import StrategyRevisionView, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services import user_data
from pathfinder.services.strategies import abandoned_mint
from pathfinder.services.strategies.abandoned_mint import delete_released_mint
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from pathfinder.services.strategies.revision_ops import (
    discard_turn_strategy_writes,
    restore_revision,
)
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.services.strategies.wdk_sync import (
    ChatOwner,
    WdkChatSpec,
    upsert_chat,
)
from pathfinder.services.user_data import purge_user_data

_SITE = "plasmodb"
_MINTED = 777
_REMINTED = 778
_ADOPTED = 42


@dataclass(frozen=True)
class _Summary:
    strategy_id: int


@dataclass
class _FakeStrategyApi:
    """Answers the saved mark and records the strategies it deletes."""

    deleted: list[int] = field(default_factory=list)

    async def list_strategies(self) -> list[_Summary]:
        return [_Summary(_MINTED), _Summary(_REMINTED), _Summary(_ADOPTED)]

    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        return WDKStrategyDetails(
            strategy_id=strategy_id,
            name="c",
            root_step_id=1,
            step_tree=WDKStepTree(step_id=1),
        )

    async def delete_strategy(self, strategy_id: int) -> None:
        self.deleted.append(strategy_id)


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


def _leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_a",
        search_name="GenesByTaxon",
        parameters={"organism": MultiPickValue(values=["Pf3D7"])},
    )


async def _seed_thread(db_session: AsyncSession, user: User) -> UUID:
    conv_id = uuid4()
    db_session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conv_id,
            user_id=user.id,
            site_id=_SITE,
            name="c",
        )
    )
    await db_session.flush()
    await db_session.commit()
    return conv_id


def _deps(
    conv_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    wdk_strategy_id: int,
) -> tuple[StrategyMutationContext, StrategyGraph]:
    session = StrategySession(site_id=_SITE)
    graph = StrategyGraph(graph_id=str(conv_id), name="c", site_id=_SITE)
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(_leaf()))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_a": 100}, wdk_strategy_id=wdk_strategy_id
    )
    deps = StrategyMutationContext(
        site_id=_SITE,
        strategy_session=session,
        conversation_id=conv_id,
        db_session_factory=session_maker,
    )
    return deps, graph


def _sync_result(wdk_strategy_id: int, *, created: bool) -> SyncResult:
    return SyncResult(
        wdk_strategy_id=wdk_strategy_id,
        wdk_url="http://example.invalid",
        root_step_id=100,
        counts={},
        root_count=None,
        zero_step_ids=[],
        step_count=1,
        created_wdk_strategy=created,
    )


async def _persist(
    conv_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    wdk_strategy_id: int,
    *,
    created: bool,
) -> None:
    deps, graph = _deps(conv_id, session_maker, wdk_strategy_id)
    await persist_strategy_ast_to_conversation(
        deps=deps,
        graph=graph,
        sync_result=_sync_result(wdk_strategy_id, created=created),
    )


async def _provenance(
    session_maker: async_sessionmaker[AsyncSession], conv_id: UUID
) -> bool:
    async with session_maker() as verify:
        row = await ConversationRepository(verify).get_strategy(conv_id)
    return row.wdk_strategy_created_here


async def _adopt(db_session: AsyncSession, user: User) -> UUID:
    """Open one of the user's own website strategies in a new thread."""
    conversation = await upsert_chat(
        conv_repo=ConversationRepository(db_session),
        owner=ChatOwner(user_id=user.id, assistant_id=PATHFINDER_ASSISTANT_ID),
        site_id=_SITE,
        created_here=False,
        spec=WdkChatSpec(
            wdk_id=_ADOPTED,
            name="from the website",
            strategy_ast=StrategyAst(record_type="transcript", root=_leaf()),
            record_type="transcript",
            is_saved=True,
            step_count=1,
        ),
    )
    await db_session.commit()
    return conversation.id


async def _latest_revision_id(
    session_maker: async_sessionmaker[AsyncSession], conv_id: UUID
) -> int:
    async with session_maker() as session:
        latest = await StrategyRevisionRepository(session).latest(conv_id)
    assert latest is not None
    return latest.id


async def _previous_revision(
    session_maker: async_sessionmaker[AsyncSession], conv_id: UUID
) -> StrategyRevisionView:
    """The snapshot the thread held before its newest one."""
    async with session_maker() as session:
        history = await StrategyRevisionRepository(session).newest(conv_id, limit=2)
    assert len(history) == 2
    return history[1]


async def _discard(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
    *,
    pre_turn_revision_id: int,
) -> None:
    async with session_maker() as session:
        discarded = await discard_turn_strategy_writes(
            session,
            conversation_id=conv_id,
            pre_turn_revision_id=pre_turn_revision_id,
        )
        await session.commit()
    await delete_released_mint(discarded.release)
    assert discarded.undone is True


async def _purged_from_wdk(
    session_maker: async_sessionmaker[AsyncSession],
    user: User,
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
) -> list[int]:
    api = _FakeStrategyApi()
    monkeypatch.setattr(user_data, "get_strategy_api", lambda _site: api)
    token = application_id_ctx.set("pathfinder")
    try:
        async with session_maker() as session:
            await purge_user_data(
                session=session,
                user_id=user.id,
                site_id=_SITE,
                delete_wdk=True,
                memory_store=memory_store,
            )
    finally:
        application_id_ctx.reset(token)
    return api.deleted


async def _stored_strategy_id(
    session_maker: async_sessionmaker[AsyncSession], conv_id: UUID
) -> int | None:
    async with session_maker() as verify:
        row = await ConversationRepository(verify).get_strategy(conv_id)
    return row.wdk_strategy_id


async def test_a_minted_strategy_is_recorded_as_pathfinders(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    conv_id = await _seed_thread(db_session, seed_user)

    await _persist(conv_id, session_maker, _MINTED, created=True)

    assert await _provenance(session_maker, conv_id) is True


async def test_a_later_update_only_sync_keeps_the_minted_record(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    conv_id = await _seed_thread(db_session, seed_user)
    await _persist(conv_id, session_maker, _MINTED, created=True)

    await _persist(conv_id, session_maker, _MINTED, created=False)

    assert await _provenance(session_maker, conv_id) is True


async def test_a_strategy_opened_from_the_website_is_not_pathfinders(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    conv_id = await _adopt(db_session, seed_user)

    assert await _provenance(session_maker, conv_id) is False


async def test_reopening_a_built_strategy_from_the_website_keeps_the_claim(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    app_memory_store: MemoryStore,
) -> None:
    """The row already holds that id's provenance, so an adoption leaves it."""
    conv_id = await _seed_thread(db_session, seed_user)
    await _persist(conv_id, session_maker, _ADOPTED, created=True)

    reopened = await _adopt(db_session, seed_user)

    assert reopened == conv_id
    assert await _provenance(session_maker, conv_id) is True
    assert await _purged_from_wdk(
        session_maker, seed_user, monkeypatch, app_memory_store
    ) == [_ADOPTED]


async def test_syncing_an_adopted_strategy_does_not_claim_it(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    conv_id = await _adopt(db_session, seed_user)

    await _persist(conv_id, session_maker, _ADOPTED, created=False)

    assert await _provenance(session_maker, conv_id) is False


async def test_restoring_a_revision_keeps_the_claim_it_recorded(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A thread that minted twice goes back to the first mint, still claimed."""
    conv_id = await _seed_thread(db_session, seed_user)
    await _persist(conv_id, session_maker, _MINTED, created=True)
    await _persist(conv_id, session_maker, _REMINTED, created=True)
    revision = await _previous_revision(session_maker, conv_id)

    async with session_maker() as session:
        release = await restore_revision(session, revision=revision)
        await session.commit()
    await delete_released_mint(release)

    assert await _stored_strategy_id(session_maker, conv_id) == _MINTED
    assert await _provenance(session_maker, conv_id) is True


async def test_restoring_a_revision_keeps_an_adopted_strategy_unclaimed(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A mint on top of an adopted strategy does not survive the restore."""
    conv_id = await _adopt(db_session, seed_user)
    await _persist(conv_id, session_maker, _MINTED, created=True)
    revision = await _previous_revision(session_maker, conv_id)

    async with session_maker() as session:
        release = await restore_revision(session, revision=revision)
        await session.commit()
    await delete_released_mint(release)

    assert await _stored_strategy_id(session_maker, conv_id) == _ADOPTED
    assert await _provenance(session_maker, conv_id) is False


async def test_a_stopped_turn_leaves_the_website_strategy_on_veupathdb(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    app_memory_store: MemoryStore,
) -> None:
    """A refused update mints a replacement; discarding it gives the mint back."""
    conv_id = await _adopt(db_session, seed_user)
    pre_turn = await _latest_revision_id(session_maker, conv_id)
    await _persist(conv_id, session_maker, _MINTED, created=True)
    released = _FakeStrategyApi()
    monkeypatch.setattr(abandoned_mint, "get_strategy_api", lambda _site: released)

    await _discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert released.deleted == [_MINTED]

    assert await _stored_strategy_id(session_maker, conv_id) == _ADOPTED
    assert await _provenance(session_maker, conv_id) is False
    assert (
        await _purged_from_wdk(session_maker, seed_user, monkeypatch, app_memory_store)
        == []
    )
