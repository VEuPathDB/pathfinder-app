"""Absent-row semantics and lifecycle of the strategy side table."""

from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.persistence.models import (
    ConversationStrategy,
    ConversationStrategyView,
)
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.services.conversations.responses import build_conversation_summary
from pathfinder.services.user_data import purge_user_data


def _ast() -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
    )


async def _thread(user_id: UUID, name: str = "c") -> UUID:
    async with async_session_factory() as session:
        conversation = await ConversationRepository(session).create(
            user_id,
            "plasmodb",
            name=name,
        )
        await session.commit()
        return conversation.id


async def _side_row_count() -> int:
    async with async_session_factory() as session:
        return (
            await session.scalar(
                select(func.count()).select_from(ConversationStrategy),
            )
        ) or 0


async def test_a_new_thread_has_no_strategy_row(authed_user_id: UUID) -> None:
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as session:
        found = await ConversationRepository(session).get_with_strategy(conversation_id)

    assert found is not None
    assert found[1] == ConversationStrategyView()
    assert await _side_row_count() == 0


async def test_an_absent_row_reads_as_a_strategy_that_was_never_built(
    authed_user_id: UUID,
) -> None:
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as session:
        found = await ConversationRepository(session).get_with_strategy(conversation_id)
        assert found is not None
        summary = build_conversation_summary(*found)

    assert summary.wdk_strategy_id is None
    assert summary.record_type is None
    assert summary.is_saved is False
    assert summary.step_count == 0
    assert summary.estimated_size is None
    assert summary.gene_set_id is None
    assert summary.experiment_id is None
    assert summary.steps == []


async def test_the_first_strategy_write_creates_the_row(authed_user_id: UUID) -> None:
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=_ast(),
                record_type="transcript",
                step_count=1,
                wdk_strategy_id=777001,
                wdk_strategy_id_set=True,
            ),
        )
        await session.commit()

    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)

    assert await _side_row_count() == 1
    assert strategy.wdk_strategy_id == 777001
    assert strategy.record_type == "transcript"
    assert strategy.step_count == 1
    root = strategy.strategy_ast["root"]
    assert isinstance(root, dict)
    assert root["id"] == "step_a"
    assert root["searchName"] == "GenesByTaxon"
    assert strategy.is_saved is False
    assert strategy.imported_saved_strategy_ids == []


async def test_a_second_write_updates_the_same_row(authed_user_id: UUID) -> None:
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        await repo.update_conversation(
            conversation_id,
            ConversationUpdate(strategy_ast=_ast(), step_count=1),
        )
        await repo.update_conversation(
            conversation_id,
            ConversationUpdate(estimated_size=137, estimated_size_set=True),
        )
        await session.commit()

    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)

    assert strategy.estimated_size == 137
    assert strategy.step_count == 1
    assert await _side_row_count() == 1


async def test_clearing_blanks_the_built_strategy_and_keeps_the_links(
    authed_user_id: UUID,
) -> None:
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        await repo.update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=_ast(),
                step_count=1,
                wdk_strategy_id=777002,
                wdk_strategy_id_set=True,
                gene_set_auto_imported=True,
            ),
        )
        await repo.clear_strategy(conversation_id)
        await session.commit()

    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)

    assert strategy.strategy_ast == {}
    assert strategy.wdk_strategy_id is None
    assert strategy.step_count == 0
    assert strategy.gene_set_auto_imported is True


async def test_clearing_a_thread_that_never_built_creates_nothing(
    authed_user_id: UUID,
) -> None:
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as session:
        await ConversationRepository(session).clear_strategy(conversation_id)
        await session.commit()

    assert await _side_row_count() == 0


async def test_deleting_the_thread_removes_its_strategy(authed_user_id: UUID) -> None:
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        await repo.update_conversation(
            conversation_id,
            ConversationUpdate(strategy_ast=_ast(), step_count=1),
        )
        await session.commit()
    assert await _side_row_count() == 1

    async with async_session_factory() as session:
        await ConversationRepository(session).delete(conversation_id)
        await session.commit()

    assert await _side_row_count() == 0


async def test_two_threads_cannot_claim_the_same_wdk_strategy(
    authed_user_id: UUID,
) -> None:
    first = await _thread(authed_user_id, name="first")
    second = await _thread(authed_user_id, name="second")

    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        await repo.update_conversation(
            first,
            ConversationUpdate(wdk_strategy_id=777003, wdk_strategy_id_set=True),
        )
        await session.commit()

    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        with pytest.raises(IntegrityError, match="wdk_strategy_id"):
            await repo.update_conversation(
                second,
                ConversationUpdate(wdk_strategy_id=777003, wdk_strategy_id_set=True),
            )


async def test_purging_a_user_takes_the_strategy_rows(authed_user_id: UUID) -> None:
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(strategy_ast=_ast(), step_count=1),
        )
        await session.commit()

    async with async_session_factory() as session:
        await purge_user_data(
            session=session,
            user_id=authed_user_id,
            site_id=None,
            delete_wdk=True,
        )

    assert await _side_row_count() == 0


async def test_a_read_returns_what_another_session_committed(
    authed_user_id: UUID,
) -> None:
    """The strategy is written by statements, so a stale identity map must not win."""
    conversation_id = await _thread(authed_user_id)

    async with async_session_factory() as reader:
        repo = ConversationRepository(reader)
        assert await repo.get_strategy(conversation_id) == ConversationStrategyView()

        async with async_session_factory() as writer:
            await ConversationRepository(writer).update_conversation(
                conversation_id,
                ConversationUpdate(strategy_ast=_ast(), step_count=4),
            )
            await writer.commit()

        after = await repo.get_with_strategy(conversation_id)

    assert after is not None
    assert after[1].step_count == 4
