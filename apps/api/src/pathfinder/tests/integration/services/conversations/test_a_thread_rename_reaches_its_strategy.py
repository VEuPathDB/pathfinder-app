"""A thread renamed from the sidebar carries the name onto its stored strategy."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.platform.db import async_session_factory
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.service import ConversationService
from pathfinder.services.conversations.update_input import ConversationUpdateInput


async def test_a_rename_writes_the_thread_and_its_stored_strategy(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        conversation = await ConversationRepository(session).create(
            user_id=user_id,
            site_id="plasmodb",
            assistant_id=PATHFINDER_ASSISTANT_ID,
            name="Kinase hunt",
        )
        session.add(
            ConversationStrategy(
                conversation_id=conversation.id,
                strategy_ast=StrategyAst(
                    record_type="transcript",
                    name="Kinase hunt",
                    root=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
                ).model_dump(by_alias=True, exclude_none=True, mode="json"),
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        response = await ConversationService(session).update(
            conversation.id,
            user_id,
            ConversationUpdateInput(
                name="Exported kinases",
                strategy_ast=None,
                wdk_strategy_id=None,
                wdk_strategy_id_set=False,
                is_saved=None,
                is_saved_set=False,
            ),
        )
        await session.commit()

    async with async_session_factory() as session:
        stored = await ConversationRepository(session).get_strategy(conversation.id)
    assert response.name == "Exported kinases"
    assert stored.strategy_ast.get("name") == "Exported kinases"
