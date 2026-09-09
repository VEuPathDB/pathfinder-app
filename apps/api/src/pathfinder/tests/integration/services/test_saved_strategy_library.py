"""The saved-strategy library lists the caller's saved strategies on one site."""

from __future__ import annotations

from uuid import UUID, uuid4

from assistant_core.platform.db import async_session_factory
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.saved_library import list_saved_strategies


def _ast() -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
    )


async def _saved_thread(
    user_id: UUID,
    *,
    name: str,
    site_id: str = "plasmodb",
    wdk_strategy_id: int,
    is_saved: bool = True,
    estimated_size: int = 227,
) -> UUID:
    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        conversation = await repo.create(
            user_id,
            site_id,
            assistant_id=PATHFINDER_ASSISTANT_ID,
            name=name,
        )
        await repo.update_conversation(
            conversation.id,
            ConversationUpdate(
                record_type="transcript",
                wdk_strategy_id=wdk_strategy_id,
                wdk_strategy_id_set=True,
                is_saved=is_saved,
                is_saved_set=True,
                step_count=3,
                strategy_ast=_ast(),
                estimated_size=estimated_size,
                estimated_size_set=True,
            ),
        )
        await session.commit()
        return conversation.id


async def _other_user() -> UUID:
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()
    return user_id


async def test_the_listing_holds_only_the_callers_saved_rows_on_the_site(
    authed_user_id: UUID,
) -> None:
    mine = await _saved_thread(
        authed_user_id, name="Pf protease union (text OR GO)", wdk_strategy_id=330534203
    )
    await _saved_thread(
        authed_user_id, name="unsaved work", wdk_strategy_id=330534204, is_saved=False
    )
    await _saved_thread(
        authed_user_id,
        name="other site",
        site_id="toxodb",
        wdk_strategy_id=330534205,
    )
    stranger = await _other_user()
    await _saved_thread(stranger, name="not mine", wdk_strategy_id=330534206)

    listing = await list_saved_strategies(
        async_session_factory, user_id=authed_user_id, site_id="plasmodb"
    )

    assert [entry.name for entry in listing] == ["Pf protease union (text OR GO)"]
    entry = listing[0]
    assert entry.conversation_id == str(mine)
    assert entry.wdk_strategy_id == 330534203
    assert entry.record_type == "transcript"
    assert entry.root_count == 227
    assert entry.step_count == 3
