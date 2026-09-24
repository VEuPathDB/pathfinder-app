"""The rating rows: one per message per user, the latest rating wins."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import calling_application
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import array, insert
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.message_rating import Rating, StandingRating, WithheldCase
from pathfinder.persistence.models import MessageRating, MessageRatingView

__all__ = ["MessageRatingRepository"]

_WITHHELD = TypeAdapter(list[WithheldCase])


def _merged(
    current: Sequence[WithheldCase], added: Sequence[WithheldCase]
) -> list[WithheldCase]:
    """Every withheld case once per key; a later value replaces an earlier one."""
    by_key = {case.key: case for case in current}
    by_key.update({case.key: case for case in added})
    return list(by_key.values())


class MessageRatingRepository:
    """Read and write the rating rows of one user's messages."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _row(
        self,
        *,
        message_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
    ) -> MessageRating:
        """The row of this message and user, created when absent, locked for update."""
        await self.session.execute(
            insert(MessageRating)
            .values(
                message_id=message_id,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            .on_conflict_do_nothing(constraint="uq_message_ratings_message_user"),
        )
        row = await self.session.scalar(
            select(MessageRating)
            .where(
                MessageRating.message_id == message_id,
                MessageRating.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True),
        )
        if row is None:
            msg = f"no rating row for message {message_id}"
            raise LookupError(msg)
        return row

    async def get(self, message_id: UUID, *, user_id: UUID) -> MessageRatingView | None:
        row = await self.session.scalar(
            select(MessageRating).where(
                MessageRating.message_id == message_id,
                MessageRating.user_id == user_id,
            ),
        )
        return None if row is None else MessageRatingView.model_validate(row)

    async def set_rating(
        self,
        *,
        message_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        rating: Rating | None,
    ) -> MessageRatingView:
        """Record the rating, or clear it with ``None``; the case keys stay."""
        row = await self._row(
            message_id=message_id, conversation_id=conversation_id, user_id=user_id
        )
        row.rating = rating
        row.rated_at = None if rating is None else datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(row)
        return MessageRatingView.model_validate(row)

    async def record_turn_cases(
        self,
        *,
        message_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        keys: Sequence[str],
        withheld: Sequence[WithheldCase],
    ) -> None:
        """Add a turn's case keys and withheld values to the message's row."""
        row = await self._row(
            message_id=message_id, conversation_id=conversation_id, user_id=user_id
        )
        current = MessageRatingView.model_validate(row)
        row.case_keys = list(dict.fromkeys([*current.case_keys, *keys]))
        row.withheld_cases = _WITHHELD.dump_python(
            _merged(current.withheld_cases, withheld), mode="json"
        )
        await self.session.flush()

    async def set_withheld(
        self,
        message_id: UUID,
        *,
        user_id: UUID,
        withheld: Sequence[WithheldCase],
    ) -> None:
        row = await self.session.scalar(
            select(MessageRating).where(
                MessageRating.message_id == message_id,
                MessageRating.user_id == user_id,
            ),
        )
        if row is None:
            return
        row.withheld_cases = _WITHHELD.dump_python(list(withheld), mode="json")
        await self.session.flush()

    async def list_rated(
        self, conversation_id: UUID, *, user_id: UUID
    ) -> list[MessageRatingView]:
        """The thread's rated messages, oldest rating first."""
        rows = await self.session.scalars(
            select(MessageRating)
            .where(
                MessageRating.conversation_id == conversation_id,
                MessageRating.user_id == user_id,
                MessageRating.rating.is_not(None),
            )
            .order_by(MessageRating.rated_at, MessageRating.id),
        )
        return [MessageRatingView.model_validate(row) for row in rows]

    async def others_for_keys(
        self,
        *,
        user_id: UUID,
        keys: Sequence[str],
        excluding: UUID | None,
    ) -> list[StandingRating]:
        """The standing ratings of other messages that name any of ``keys``."""
        if not keys:
            return []
        query = (
            select(MessageRating)
            .join(Conversation, Conversation.id == MessageRating.conversation_id)
            .where(
                MessageRating.user_id == user_id,
                MessageRating.rating.is_not(None),
                MessageRating.case_keys.has_any(array(list(keys))),
                Conversation.application_id == calling_application(),
            )
        )
        if excluding is not None:
            query = query.where(MessageRating.message_id != excluding)
        rows = await self.session.scalars(query)
        return [
            StandingRating.model_validate(
                MessageRatingView.model_validate(row), from_attributes=True
            )
            for row in rows
        ]
