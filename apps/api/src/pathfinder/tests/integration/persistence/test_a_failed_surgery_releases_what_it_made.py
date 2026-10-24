from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db

from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.service import ConversationService
from pathfinder.services.strategies import abandoned_mint
from pathfinder.tests.integration.persistence._fake_eda import (
    FakeEda,
    install_fake_eda,
)
from pathfinder.tests.integration.persistence._thread_surgery import (
    EDA_DATASET,
    FIRST_PUSHED_WDK_STRATEGY_ID,
    SOURCE_WDK_STRATEGY_ID,
    FakePush,
    FourTurns,
    add_analysis_state,
    bind_analysis,
    bound_analysis,
    four_turn_thread,
    gametocyte_filter,
    install_fake_push,
    seed_user,
)
from pathfinder.tests.integration.services.strategies._mint_release import (
    FakeStrategyApi,
)
from pathfinder.transport.http.routers.conversations.revert import (
    RevertRequest,
    revert_to_message,
)

REFUSED = "the surgery could not be written"
pytestmark = pytest.mark.usefixtures("db_cleaner")


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeStrategyApi:
    api = FakeStrategyApi()
    monkeypatch.setattr(abandoned_mint, "get_strategy_api", lambda _site: api)
    return api


async def _refuse(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError(REFUSED)


async def _thread_with_a_study(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[FourTurns, UUID, FakePush, FakeEda]:
    push = install_fake_push(monkeypatch)
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
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4")
    return thread, user_id, push, eda


async def test_a_revert_whose_commit_fails_deletes_its_mint(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", _refuse)
        with pytest.raises(RuntimeError, match=REFUSED):
            await revert_to_message(
                thread.conversation_id,
                RevertRequest(message_id=thread.user_three),
                session,
                user_id,
            )

    assert (push.pushed_strategy_ids, site.deleted) == (
        [FIRST_PUSHED_WDK_STRATEGY_ID],
        [FIRST_PUSHED_WDK_STRATEGY_ID],
    )
    assert SOURCE_WDK_STRATEGY_ID not in site.deleted


async def test_a_revert_whose_commit_fails_deletes_the_document_it_opened(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, _, eda = await _thread_with_a_study(monkeypatch)
    del eda.documents["a1b2c3d4"]
    eda.document("z9y8x7w6")
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="z9y8x7w6",
    )
    await bind_analysis(thread.conversation_id, analysis_id="z9y8x7w6")

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", _refuse)
        with pytest.raises(RuntimeError, match=REFUSED):
            await revert_to_message(
                thread.conversation_id,
                RevertRequest(message_id=thread.user_three),
                session,
                user_id,
            )

    assert (eda.created, eda.deleted) == (
        [(EDA_DATASET, "gametocyte rows")],
        ["fresh1"],
    )
    assert site.deleted == [FIRST_PUSHED_WDK_STRATEGY_ID]
    still = await bound_analysis(thread.conversation_id)
    assert still is not None
    assert still.analysis_id == "z9y8x7w6"


async def test_a_branch_whose_commit_fails_deletes_its_document(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, push, eda = await _thread_with_a_study(monkeypatch)

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", _refuse)
        with pytest.raises(RuntimeError, match=REFUSED):
            await ConversationService(session).fork(
                thread.conversation_id,
                user_id,
                thread.answer_two,
            )

    assert (eda.deleted, site.deleted) == (["fresh1"], push.pushed_strategy_ids)
    assert eda.documents == {"a1b2c3d4": [gametocyte_filter("gametocyte")]}


async def test_a_branch_whose_snapshot_write_fails_deletes_its_document(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, push, eda = await _thread_with_a_study(monkeypatch)
    monkeypatch.setattr(StrategyRevisionRepository, "record", _refuse)

    async with db.async_session_factory() as session:
        with pytest.raises(RuntimeError, match=REFUSED):
            await ConversationService(session).fork(
                thread.conversation_id,
                user_id,
                thread.answer_two,
            )

    assert (eda.deleted, site.deleted) == (
        ["fresh1"],
        [FIRST_PUSHED_WDK_STRATEGY_ID],
    )
    assert push.pushed_strategy_ids == [FIRST_PUSHED_WDK_STRATEGY_ID]
