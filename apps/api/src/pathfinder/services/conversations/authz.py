"""Ownership of a thread together with the strategy projection beside it.

The general rule is the runtime's; this is the one lookup that also reads the
strategy this application keeps on its own table.
"""

from uuid import UUID

from assistant_core.conversation.authz import owned_by_caller

from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.platform.errors import ErrorCode, ForbiddenError, NotFoundError


async def get_owned_thread(
    conv_repo: ConversationRepository,
    conversation_id: UUID,
    user_id: UUID,
) -> ConversationWithStrategy:
    """The conversation and its strategy projection: 404 when none exists, 403 when another user owns it."""
    found = await conv_repo.get_with_strategy(conversation_id)
    if found is None:
        raise NotFoundError(
            code=ErrorCode.STRATEGY_NOT_FOUND,
            title="Strategy not found",
        )
    if not owned_by_caller(found[0], user_id):
        raise ForbiddenError
    return found
