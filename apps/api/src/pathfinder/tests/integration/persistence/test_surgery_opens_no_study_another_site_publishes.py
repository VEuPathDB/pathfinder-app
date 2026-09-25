"""A branch and a revert open no study that another site publishes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from sqlalchemy import text

from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests._support.published_studies import published_on
from pathfinder.tests.integration.persistence._fake_eda import install_fake_eda
from pathfinder.tests.integration.persistence._thread_surgery import (
    EDA_DATASET,
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


async def test_a_branch_opens_no_study_vectorbase_publishes(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    eda.user_study = False
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    eda.document("a1b2c3d4", [gametocyte_filter("gametocyte")])
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="a1b2c3d4",
        filters=[gametocyte_filter("gametocyte")],
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4")

    async with (
        published_on("vectorbase", EDA_DATASET, organism="Anopheles gambiae PEST"),
        db.async_session_factory() as session,
    ):
        forked = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_four,
            user_id=user_id,
        )
        await session.commit()
        fork_id: UUID = forked.id

    assert await bound_analysis(fork_id) is None
    assert eda.created == []


async def test_a_revert_does_not_rebind_a_study_vectorbase_publishes(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    eda.user_study = False
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    eda.document("a1b2c3d4", [gametocyte_filter("gametocyte")])
    eda.document("e5f6a7b8", [gametocyte_filter("ring")])
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_two,
        analysis_id="a1b2c3d4",
        filters=[gametocyte_filter("gametocyte")],
    )
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="e5f6a7b8",
        filters=[gametocyte_filter("ring")],
    )
    await bind_analysis(thread.conversation_id, analysis_id="e5f6a7b8")

    async with (
        published_on("vectorbase", EDA_DATASET, organism="Anopheles gambiae PEST"),
        db.async_session_factory() as session,
    ):
        await revert_conversation_to_message(
            session,
            conversation_id=thread.conversation_id,
            target_message_id=thread.user_three,
            user_id=user_id,
        )
        await session.commit()

    binding = await bound_analysis(thread.conversation_id)
    assert binding is not None
    assert binding.analysis_id == "e5f6a7b8"
    assert eda.patched == []
    assert eda.created == []
