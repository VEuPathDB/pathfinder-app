"""The count on a thread's EDA analysis, across a revert and a branch.

A preview counts the subset the analysis holds. Surgery that puts another
subset back leaves the count describing nothing, so the export waits for a new
one; a branch authors its own document and starts uncounted.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from sqlalchemy import text

from pathfinder.persistence.repositories.conversation_analysis import (
    mark_analysis_previewed_row,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests.integration.persistence._fake_eda import install_fake_eda
from pathfinder.tests.integration.persistence._thread_surgery import (
    add_analysis_state,
    bind_analysis,
    bound_analysis,
    four_turn_thread,
    gametocyte_filter,
    install_fake_push,
    seed_user,
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


async def record_preview(conversation_id: UUID) -> None:
    """Count the open analysis's subset, as a preview does."""
    async with db.async_session_factory() as session:
        await mark_analysis_previewed_row(session, conversation_id=conversation_id)
        await session.commit()


async def _revert(
    *, conversation_id: UUID, target_message_id: UUID, user_id: UUID
) -> None:
    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=target_message_id,
            user_id=user_id,
        )
        await session.commit()


async def _fork(
    *, source_conversation_id: UUID, from_message_id: UUID, user_id: UUID
) -> UUID:
    async with db.async_session_factory() as session:
        forked = await fork_conversation(
            session,
            source_conversation_id=source_conversation_id,
            from_message_id=from_message_id,
            user_id=user_id,
        )
        await session.commit()
        return forked.id


async def test_a_revert_that_moves_the_subset_forgets_the_count(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The export waits for a count of the subset the revert put back."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    at_turn_two = [gametocyte_filter("gametocyte")]
    at_turn_four = [gametocyte_filter("gametocyte", "ring")]
    eda.document("a1b2c3d4", at_turn_four)
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_two,
        analysis_id="a1b2c3d4",
        filters=at_turn_two,
    )
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="a1b2c3d4",
        filters=at_turn_four,
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4", revision=2)
    await record_preview(thread.conversation_id)

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    binding = await bound_analysis(thread.conversation_id)
    assert binding is not None
    assert binding.subset_previewed is False
    assert binding.revision == 3
    assert eda.documents["a1b2c3d4"] == at_turn_two


async def test_a_revert_that_leaves_the_subset_alone_keeps_the_count(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A revert that changes no filter changes no count either."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    subset = [gametocyte_filter("gametocyte")]
    eda.document("a1b2c3d4", subset)
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_two,
        analysis_id="a1b2c3d4",
        filters=subset,
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4", revision=2)
    await record_preview(thread.conversation_id)

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    binding = await bound_analysis(thread.conversation_id)
    assert binding is not None
    assert binding.subset_previewed is True
    assert eda.patched == []


async def test_a_branch_starts_with_no_count_of_its_own_subset(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parent's count describes the parent's document, not the branch's."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    subset = [gametocyte_filter("gametocyte", "ring")]
    eda.document("a1b2c3d4", subset)
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="a1b2c3d4",
        filters=subset,
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4")
    await record_preview(thread.conversation_id)

    fork_id = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )

    branch = await bound_analysis(fork_id)
    assert branch is not None
    assert branch.analysis_id == "fresh1"
    assert branch.subset_previewed is False
    parent = await bound_analysis(thread.conversation_id)
    assert parent is not None
    assert parent.subset_previewed is True
