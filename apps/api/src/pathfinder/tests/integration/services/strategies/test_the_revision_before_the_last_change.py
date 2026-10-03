"""The revision an undo returns to is the one the turn before the last change ended on."""

from __future__ import annotations

from uuid import UUID, uuid4

from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from veupathdb.domain.strategy import CombineOp, StrategyAst

from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.revision_ops import previous_revision
from pathfinder.tests.integration.persistence._strategy_shapes import three_step_ast


async def _seed_thread() -> UUID:
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
                name="undo",
            ),
        )
        await session.commit()
    return conversation_id


def _joined(operator: CombineOp) -> StrategyAst:
    ast = three_step_ast()
    return ast.model_copy(
        update={"root": ast.root.model_copy(update={"operator": operator})}
    )


async def _write(
    conversation_id: UUID, ast: StrategyAst, *, saved: bool = False
) -> None:
    async with db.async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=ast,
                record_type="transcript",
                step_count=3,
                is_saved=saved,
                is_saved_set=True,
            ),
        )
        await session.commit()


async def _end_turn(conversation_id: UUID) -> None:
    async with db.async_session_factory() as session:
        await StrategyRevisionRepository(session).name_latest(
            conversation_id, message_id=uuid4()
        )
        await session.commit()


async def _previous(conversation_id: UUID) -> str | None:
    async with db.async_session_factory() as session:
        found = await previous_revision(session, conversation_id=conversation_id)
    return None if found is None else found.revision


async def test_the_undo_target_is_the_tree_before_the_last_turn_s_change(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    del patch_app_db_engine, db_cleaner
    conversation_id = await _seed_thread()
    await _write(conversation_id, _joined(CombineOp.INTERSECT))
    await _end_turn(conversation_id)
    await _write(conversation_id, _joined(CombineOp.MINUS))
    await _write(conversation_id, _joined(CombineOp.UNION))
    await _end_turn(conversation_id)

    assert await _previous(conversation_id) == strategy_revision(
        _joined(CombineOp.INTERSECT)
    )


async def test_a_turn_that_changed_nothing_keeps_the_same_target(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    del patch_app_db_engine, db_cleaner
    conversation_id = await _seed_thread()
    await _write(conversation_id, _joined(CombineOp.INTERSECT))
    await _end_turn(conversation_id)
    await _write(conversation_id, _joined(CombineOp.UNION))
    await _end_turn(conversation_id)
    await _end_turn(conversation_id)

    assert await _previous(conversation_id) == strategy_revision(
        _joined(CombineOp.INTERSECT)
    )


async def test_a_turn_that_only_saved_the_strategy_is_not_a_change(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    """A snapshot that differs only in what WDK records of the tree is skipped."""
    del patch_app_db_engine, db_cleaner
    conversation_id = await _seed_thread()
    await _write(conversation_id, _joined(CombineOp.INTERSECT))
    await _end_turn(conversation_id)
    await _write(conversation_id, _joined(CombineOp.UNION))
    await _end_turn(conversation_id)
    await _write(conversation_id, _joined(CombineOp.UNION), saved=True)
    await _end_turn(conversation_id)

    assert await _previous(conversation_id) == strategy_revision(
        _joined(CombineOp.INTERSECT)
    )


async def test_a_change_written_outside_a_turn_is_the_one_undone(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    del patch_app_db_engine, db_cleaner
    conversation_id = await _seed_thread()
    await _write(conversation_id, _joined(CombineOp.INTERSECT))
    await _end_turn(conversation_id)
    await _write(conversation_id, _joined(CombineOp.UNION))

    assert await _previous(conversation_id) == strategy_revision(
        _joined(CombineOp.INTERSECT)
    )


async def test_the_first_strategy_has_no_revision_before_it(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    del patch_app_db_engine, db_cleaner
    conversation_id = await _seed_thread()
    await _write(conversation_id, _joined(CombineOp.INTERSECT))
    await _end_turn(conversation_id)

    assert [await _previous(conversation_id)] == [None]
