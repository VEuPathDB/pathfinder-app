from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db

from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.services.eda import thread_surgery
from pathfinder.tests.integration.persistence._failed_surgery import (
    REFUSED,
    refuse,
    thread_with_a_study,
)
from pathfinder.tests.integration.persistence._fake_eda import FakeEda
from pathfinder.tests.integration.persistence._thread_surgery import (
    FourTurns,
    add_analysis_state,
    bind_analysis,
    bound_analysis,
)

pytestmark = pytest.mark.usefixtures("db_cleaner")


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


async def _branch(thread: FourTurns, user_id: UUID) -> UUID:
    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_two,
            user_id=user_id,
        )
        await session.commit()
        return fork.id


async def _revert(thread: FourTurns, user_id: UUID) -> None:
    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=thread.conversation_id,
            target_message_id=thread.user_three,
            user_id=user_id,
        )
        await session.commit()


async def _recorded_document_gone(thread: FourTurns, eda: FakeEda) -> None:
    del eda.documents["a1b2c3d4"]
    eda.document("z9y8x7w6")
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="z9y8x7w6",
    )
    await bind_analysis(thread.conversation_id, analysis_id="z9y8x7w6")


async def test_a_branch_whose_subset_is_refused_deletes_the_document_it_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, user_id, _, eda = await thread_with_a_study(monkeypatch)
    eda.refuse_patch_of = {"fresh1"}

    fork_id = await _branch(thread, user_id)

    assert (eda.deleted, await bound_analysis(fork_id)) == (["fresh1"], None)


async def test_a_branch_whose_binding_fails_deletes_the_document_it_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, user_id, _, eda = await thread_with_a_study(monkeypatch)
    monkeypatch.setattr(thread_surgery, "bind_analysis_row", refuse)

    with pytest.raises(RuntimeError, match=REFUSED):
        await _branch(thread, user_id)

    assert eda.deleted == ["fresh1"]


async def test_a_revert_whose_fresh_subset_is_refused_deletes_that_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, user_id, _, eda = await thread_with_a_study(monkeypatch)
    await _recorded_document_gone(thread, eda)
    eda.refuse_patch_of = {"fresh1"}

    await _revert(thread, user_id)

    kept = await bound_analysis(thread.conversation_id)
    assert kept is not None
    assert (eda.deleted, kept.analysis_id) == (["fresh1"], "z9y8x7w6")


async def test_a_revert_whose_binding_fails_deletes_the_document_it_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, user_id, _, eda = await thread_with_a_study(monkeypatch)
    await _recorded_document_gone(thread, eda)
    monkeypatch.setattr(thread_surgery, "bind_analysis_row", refuse)

    with pytest.raises(RuntimeError, match=REFUSED):
        await _revert(thread, user_id)

    assert eda.deleted == ["fresh1"]
