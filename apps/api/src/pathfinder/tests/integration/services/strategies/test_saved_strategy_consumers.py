"""Tests for the saved-strategy consumer-tracking + deletion-guard repo helpers."""

from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.persistence.repositories.saved_strategy import (
    SavedStrategyRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


async def _make_conversation(
    *,
    user_id: UUID,
    site_id: str,
    name: str,
    imported_saved_strategy_ids: list[int] | None = None,
    is_saved: bool = False,
    wdk_strategy_id: int | None = None,
) -> UUID:
    cid = uuid4()
    async with async_session_factory() as session:
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=cid,
                user_id=user_id,
                site_id=site_id,
                name=name,
            ),
        )
        await session.flush()
        session.add(
            ConversationStrategy(
                conversation_id=cid,
                strategy_ast={},
                imported_saved_strategy_ids=imported_saved_strategy_ids or [],
                is_saved=is_saved,
                wdk_strategy_id=wdk_strategy_id,
            ),
        )
        await session.commit()
    return cid


async def test_count_consumers_per_saved_strategy_aggregates_across_conversations(
    authed_user_id: UUID,
) -> None:
    site = "plasmodb"
    saved_a = await _make_conversation(
        user_id=authed_user_id,
        site_id=site,
        name="saved A",
        is_saved=True,
        wdk_strategy_id=11111,
    )
    saved_b = await _make_conversation(
        user_id=authed_user_id,
        site_id=site,
        name="saved B",
        is_saved=True,
        wdk_strategy_id=22222,
    )
    del saved_a, saved_b
    await _make_conversation(
        user_id=authed_user_id,
        site_id=site,
        name="consumer 1",
        imported_saved_strategy_ids=[11111],
    )
    await _make_conversation(
        user_id=authed_user_id,
        site_id=site,
        name="consumer 2",
        imported_saved_strategy_ids=[11111, 22222],
    )

    async with async_session_factory() as db:
        repo = SavedStrategyRepository(db)
        counts = await repo.count_consumers_per_saved_strategy(
            authed_user_id,
            site,
        )

    assert counts == {11111: 2, 22222: 1}


async def test_list_consumers_excludes_self_and_other_users(
    authed_user_id: UUID,
) -> None:
    site = "plasmodb"
    saved_id = 33333
    self_conv = await _make_conversation(
        user_id=authed_user_id,
        site_id=site,
        name="saved self",
        is_saved=True,
        wdk_strategy_id=saved_id,
        imported_saved_strategy_ids=[saved_id],
    )
    other_conv = await _make_conversation(
        user_id=authed_user_id,
        site_id=site,
        name="other consumer",
        imported_saved_strategy_ids=[saved_id],
    )

    async with async_session_factory() as db:
        repo = SavedStrategyRepository(db)
        consumers = await repo.list_consumers_of_saved_strategy(
            authed_user_id,
            saved_id,
            exclude_conversation_id=self_conv,
        )

    consumer_ids = {c.id for c in consumers}
    assert other_conv in consumer_ids
    assert self_conv not in consumer_ids


async def test_imported_saved_strategy_ids_persists_via_update_conversation(
    authed_user_id: UUID,
) -> None:
    site = "plasmodb"
    cid = await _make_conversation(
        user_id=authed_user_id,
        site_id=site,
        name="consumer",
    )

    async with async_session_factory() as db:
        repo = ConversationRepository(db)
        await repo.update_conversation(
            cid,
            ConversationUpdate(imported_saved_strategy_ids=[44444, 55555]),
        )
        await db.commit()

    async with async_session_factory() as db:
        repo = ConversationRepository(db)
        conv = await repo.get_strategy(cid)
        assert conv.imported_saved_strategy_ids == [44444, 55555]


@pytest.mark.parametrize("strategy_to_count", [99991, 99992])
async def test_count_returns_zero_when_no_consumers(
    authed_user_id: UUID,
    strategy_to_count: int,
) -> None:
    site = "plasmodb"
    await _make_conversation(
        user_id=authed_user_id,
        site_id=site,
        name="lonely",
        is_saved=True,
        wdk_strategy_id=strategy_to_count,
    )
    async with async_session_factory() as db:
        repo = SavedStrategyRepository(db)
        counts = await repo.count_consumers_per_saved_strategy(
            authed_user_id,
            site,
        )
    assert counts.get(strategy_to_count, 0) == 0
