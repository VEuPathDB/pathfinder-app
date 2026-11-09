from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from sqlalchemy import text

from pathfinder.assistants.copies import copy_rewrite
from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.fork import (
    CopyTerms,
    copy_conversation,
    fork_conversation,
)
from pathfinder.tests.integration.persistence._thread_surgery import (
    four_turn_thread,
    install_fake_push,
    seed_user,
)

OWNERS_SAVED_STRATEGY = 4242


@pytest.fixture
async def checkpoint_tables(patch_app_db_engine: None) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield
    async with db.async_session_factory() as session:
        await session.execute(
            text("TRUNCATE TABLE checkpoints, checkpoint_blobs, checkpoint_writes")
        )
        await session.commit()


async def _imports(conversation_id: UUID) -> list[int]:
    async with db.async_session_factory() as session:
        row = await session.get(ConversationStrategy, conversation_id)
        assert row is not None
        return list(row.imported_saved_strategy_ids)


@pytest.mark.usefixtures("db_cleaner", "checkpoint_tables")
async def test_a_copy_drops_the_owners_imports_and_a_branch_keeps_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_push(monkeypatch)
    owner = await seed_user()
    viewer = await seed_user()
    thread = await four_turn_thread(owner)
    async with db.async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            thread.conversation_id,
            ConversationUpdate(imported_saved_strategy_ids=[OWNERS_SAVED_STRATEGY]),
        )
        await session.commit()
    rewrite = copy_rewrite(PATHFINDER_ASSISTANT_ID)
    assert rewrite is not None

    async with db.async_session_factory() as session:
        source = await session.get(Conversation, thread.conversation_id)
        assert source is not None
        copy = await copy_conversation(
            session,
            source=source,
            user_id=viewer,
            terms=CopyTerms(rewrite=rewrite, keep_owner_reads=False),
        )
        branch = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_four,
            user_id=owner,
        )
        await session.commit()
        copy_id, branch_id = copy.id, branch.id

    assert await _imports(copy_id) == []
    assert await _imports(branch_id) == [OWNERS_SAVED_STRATEGY]
