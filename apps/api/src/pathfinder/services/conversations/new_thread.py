from __future__ import annotations

from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.services.conversations.fork_strategy import branch_mint
from pathfinder.services.conversations.responses import (
    ConversationResponse,
    build_conversation_summary,
)
from pathfinder.services.conversations.surgery_commit import (
    SurgeryMade,
    commit_or_release,
)
from pathfinder.services.eda.thread_surgery import bound_document


async def settle_new_thread(
    session: AsyncSession, thread: Conversation
) -> ConversationResponse:
    """Commit a branch or a copy and answer with its summary."""
    await commit_or_release(
        session,
        SurgeryMade(
            mint=await branch_mint(session, thread),
            document=await bound_document(session, conversation_id=thread.id),
        ),
    )
    refreshed = await ConversationRepository(session).get_with_strategy(thread.id)
    if refreshed is None:
        raise NotFoundError(
            code=ErrorCode.STRATEGY_NOT_FOUND, title="Strategy not found"
        )
    return build_conversation_summary(*refreshed, site_id=refreshed[0].site_id)
