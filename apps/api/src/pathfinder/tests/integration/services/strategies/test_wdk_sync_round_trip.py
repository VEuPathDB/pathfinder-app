"""Importing a WDK strategy lands in the side table and reads back from it."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.db import async_session_factory
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.saved_strategy import (
    SavedStrategyRepository,
)
from pathfinder.services.strategies.wdk_sync import (
    WdkChatSpec,
    plan_needs_detail_fetch,
    upsert_chat,
)

WDK_ID = 881001


def _spec(name: str, *, step_count: int = 1) -> WdkChatSpec:
    return WdkChatSpec(
        wdk_id=WDK_ID,
        name=name,
        strategy_ast=StrategyAst(
            record_type="transcript",
            root=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
        ),
        record_type="transcript",
        is_saved=True,
        step_count=step_count,
    )


async def test_importing_a_wdk_strategy_creates_the_side_row(
    authed_user_id: UUID,
) -> None:
    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        conversation = await upsert_chat(
            conv_repo=repo,
            user_id=authed_user_id,
            site_id="plasmodb",
            spec=_spec("imported"),
        )
        await session.commit()
        conversation_id = conversation.id

    async with async_session_factory() as session:
        found = await SavedStrategyRepository(session).get_by_wdk_strategy_id(
            authed_user_id,
            WDK_ID,
        )

    assert found is not None
    conversation, strategy = found
    assert conversation.id == conversation_id
    assert strategy.wdk_strategy_id == WDK_ID
    assert strategy.record_type == "transcript"
    assert strategy.is_saved is True
    assert strategy.step_count == 1
    assert plan_needs_detail_fetch(strategy) is False


async def test_a_second_import_updates_the_same_thread(authed_user_id: UUID) -> None:
    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        first = await upsert_chat(
            conv_repo=repo,
            user_id=authed_user_id,
            site_id="plasmodb",
            spec=_spec("imported"),
        )
        await session.commit()
        first_id = first.id

    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        second = await upsert_chat(
            conv_repo=repo,
            user_id=authed_user_id,
            site_id="plasmodb",
            spec=_spec("renamed upstream", step_count=6),
        )
        await session.commit()

        assert second.id == first_id
        assert second.name == "renamed upstream"
        second_strategy = await repo.get_strategy(second.id)
        assert second_strategy.wdk_strategy_id == WDK_ID
        assert second_strategy.step_count == 6
