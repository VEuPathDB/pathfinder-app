"""Delete the WDK strategy a test's conversation pushed to the test account."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.db import async_session_factory
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import get_strategy_api

from pathfinder.persistence.repositories import ConversationRepository


async def delete_the_threads_strategy(
    site_id: str, conversation_id: UUID, token: str | None
) -> None:
    """Delete the strategy the thread holds on the site, when it holds one."""
    if token is None:
        return
    async with async_session_factory() as session:
        view = await ConversationRepository(session).get_strategy(conversation_id)
    if view.wdk_strategy_id is None:
        return
    reset = veupathdb_auth_token_ctx.set(token)
    try:
        await get_strategy_api(site_id).delete_strategy(view.wdk_strategy_id)
    finally:
        veupathdb_auth_token_ctx.reset(reset)
