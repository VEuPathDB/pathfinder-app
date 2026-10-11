"""How many chat turns one user may have queued or running at once."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.repositories.thread_job import turns_in_flight
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import AppError, ErrorCode


class TooManyTurnsError(AppError):
    """The user already has as many turns running as one user may."""

    def __init__(self, *, limit: int) -> None:
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            title="Too many turns running",
            status=429,
            detail=(
                f"You already have {limit} conversations working. "
                "Send this once one of them has answered."
            ),
        )


async def require_a_free_turn(
    session: AsyncSession, *, user_id: UUID, conversation_id: UUID
) -> None:
    """Refuse a turn while the user's other conversations hold every slot."""
    limit = get_settings().max_turns_in_flight_per_user
    held = await turns_in_flight(session, user_id=user_id, other_than=conversation_id)
    if held >= limit:
        raise TooManyTurnsError(limit=limit)
