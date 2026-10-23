from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from sqlalchemy import text
from veupathdb.domain.strategy import StrategyAst

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests._support.mixed_record_classes import (
    MIXED_REFUSAL,
    mixed_snapshot,
)
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests.integration.persistence._thread_surgery import (
    THREE_STEPS,
    add_assistant_message,
    add_user_message,
    seed_conversation,
    seed_user,
    write_strategy,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    install_stub_api,
)


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture(autouse=True)
async def _truncate_langgraph_tables() -> AsyncIterator[None]:
    yield
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE checkpoints, checkpoint_blobs, "
                "checkpoint_writes RESTART IDENTITY",
            ),
        )
        await session.commit()


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    api = install_stub_api(monkeypatch)
    serve_orthomcl_record_classes(monkeypatch)
    return api


async def _write_the_mixed_tree(conversation_id: UUID) -> None:
    async with db.async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=StrategyAst.model_validate(mixed_snapshot()),
                record_type="sequence",
                step_count=3,
                wdk_strategy_id=330534153,
                wdk_strategy_id_set=True,
            ),
        )
        await session.commit()


async def _the_mixed_thread(user_id: UUID) -> tuple[UUID, UUID, UUID]:
    conversation_id = await seed_conversation(user_id)
    await add_user_message(conversation_id)
    await _write_the_mixed_tree(conversation_id)
    answer = await add_assistant_message(conversation_id)
    later = await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    await add_assistant_message(conversation_id)
    return conversation_id, answer, later


async def _held(conversation_id: UUID) -> ConversationStrategy:
    async with db.async_session_factory() as session:
        strategy = await session.get(ConversationStrategy, conversation_id)
    assert strategy is not None
    return strategy


async def test_a_revert_to_a_tree_of_two_record_types_posts_nothing(
    patch_app_db_engine: None, db_cleaner: None, api: StubAPI
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = await seed_user()
    conversation_id, _answer, later = await _the_mixed_thread(user_id)

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=later,
            user_id=user_id,
        )
        await session.commit()

    held = await _held(conversation_id)
    assert (api.calls, held.wdk_strategy_id, held.step_count) == ([], None, 3)
    assert held.strategy_ast["wdkPushErrors"] == {"step_join": MIXED_REFUSAL}


async def test_a_branch_of_a_tree_of_two_record_types_posts_nothing(
    patch_app_db_engine: None, db_cleaner: None, api: StubAPI
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = await seed_user()
    conversation_id, answer, _later = await _the_mixed_thread(user_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=conversation_id,
            from_message_id=answer,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    held = await _held(fork_id)
    assert (api.calls, held.wdk_strategy_id, held.step_count) == ([], None, 3)
    assert held.strategy_ast["wdkPushErrors"] == {"step_join": MIXED_REFUSAL}
