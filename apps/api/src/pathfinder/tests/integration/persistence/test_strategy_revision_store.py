"""Every strategy write appends a snapshot, and a message resolves to one."""

from __future__ import annotations

from uuid import UUID, uuid4

from assistant_core.persistence.models import Conversation, Message
from assistant_core.platform import db

from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.revision_ops import revision_at_message
from pathfinder.tests.integration.persistence._strategy_shapes import (
    four_step_ast,
    three_step_ast,
)


async def _seed_thread() -> tuple[UUID, UUID]:
    user_id, conversation_id = uuid4(), uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="revision store",
            ),
        )
        await session.commit()
    return user_id, conversation_id


async def _write_strategy(
    conversation_id: UUID,
    ast_step_ids: dict[str, int],
    *,
    created_here: bool = False,
) -> None:
    ast = (
        three_step_ast(dict(ast_step_ids))
        if len(ast_step_ids) == 3
        else four_step_ast(dict(ast_step_ids))
    )
    async with db.async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=ast,
                record_type="transcript",
                step_count=len(ast_step_ids),
                wdk_strategy_id=330534153,
                wdk_strategy_id_set=True,
                wdk_strategy_created_here=created_here,
                wdk_strategy_created_here_set=True,
            ),
        )
        await session.commit()


async def _add_message(conversation_id: UUID, role: str) -> UUID:
    message_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(
            Message(id=message_id, conversation_id=conversation_id, role=role),
        )
        await session.commit()
    return message_id


async def test_every_strategy_write_appends_a_snapshot(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    _, conversation_id = await _seed_thread()

    await _write_strategy(
        conversation_id, {"combine": 15, "protease": 13, "gameto": 14}
    )
    await _write_strategy(
        conversation_id,
        {"orthologs": 16, "combine": 15, "protease": 13, "gameto": 14},
    )

    async with db.async_session_factory() as session:
        repo = StrategyRevisionRepository(session)
        latest = await repo.latest(conversation_id)
        assert latest is not None
        assert latest.step_count == 4
        assert latest.revision == strategy_revision(
            four_step_ast(
                {"orthologs": 16, "combine": 15, "protease": 13, "gameto": 14}
            ),
        )
        earlier = await repo.at_or_before(conversation_id, latest.created_at)
        assert earlier is not None
        assert earlier.id == latest.id


async def test_a_repeat_write_of_the_same_state_appends_nothing(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    _, conversation_id = await _seed_thread()
    ids = {"combine": 15, "protease": 13, "gameto": 14}

    await _write_strategy(conversation_id, ids)
    async with db.async_session_factory() as session:
        first = await StrategyRevisionRepository(session).latest(conversation_id)
    await _write_strategy(conversation_id, ids)
    async with db.async_session_factory() as session:
        second = await StrategyRevisionRepository(session).latest(conversation_id)

    assert first is not None
    assert second is not None
    assert second.id == first.id


async def test_a_change_of_who_made_the_strategy_appends_a_snapshot(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A snapshot states the provenance of the id it names, so a change is a new one."""
    del patch_app_db_engine, db_cleaner
    _, conversation_id = await _seed_thread()
    ids = {"combine": 15, "protease": 13, "gameto": 14}

    await _write_strategy(conversation_id, ids)
    async with db.async_session_factory() as session:
        first = await StrategyRevisionRepository(session).latest(conversation_id)
    await _write_strategy(conversation_id, ids, created_here=True)
    async with db.async_session_factory() as session:
        second = await StrategyRevisionRepository(session).latest(conversation_id)

    assert first is not None
    assert first.wdk_strategy_created_here is False
    assert second is not None
    assert second.id != first.id
    assert second.wdk_strategy_created_here is True


async def test_a_message_resolves_to_the_snapshot_in_force_when_it_was_written(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """The turn-2 answer names the three-step tree, not the later four."""
    del patch_app_db_engine, db_cleaner
    _, conversation_id = await _seed_thread()

    await _write_strategy(
        conversation_id, {"combine": 15, "protease": 13, "gameto": 14}
    )
    turn_two = await _add_message(conversation_id, "assistant")
    await _write_strategy(
        conversation_id,
        {"orthologs": 16, "combine": 15, "protease": 13, "gameto": 14},
    )
    turn_four = await _add_message(conversation_id, "assistant")

    async with db.async_session_factory() as session:
        for message_id, expected in ((turn_two, 3), (turn_four, 4)):
            message = await session.get(Message, message_id)
            assert message is not None
            snapshot = await revision_at_message(session, message=message)
            assert snapshot is not None
            assert snapshot.step_count == expected


async def test_clearing_the_strategy_appends_an_empty_snapshot(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    _, conversation_id = await _seed_thread()
    await _write_strategy(
        conversation_id, {"combine": 15, "protease": 13, "gameto": 14}
    )

    async with db.async_session_factory() as session:
        await ConversationRepository(session).clear_strategy(conversation_id)
        await session.commit()

    async with db.async_session_factory() as session:
        latest = await StrategyRevisionRepository(session).latest(conversation_id)
        assert latest is not None
        assert latest.revision == ""
        assert latest.step_count == 0
        assert latest.wdk_strategy_id is None
