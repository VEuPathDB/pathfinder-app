"""Threads keyed by the WDK strategy they hold: the saved listing, the threads
that import one, and the prune of threads whose WDK strategy is gone."""

from __future__ import annotations

from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import calling_application
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
    paired,
    with_strategy,
)


class SavedStrategyRepository:
    """Data access for the WDK strategies the caller's threads hold.

    Every read is scoped to the user under the calling application.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_saved_strategies(
        self,
        user_id: UUID,
        site_id: str,
    ) -> list[ConversationWithStrategy]:
        """List the caller's saved strategies on one site, by name."""
        stmt = (
            with_strategy()
            .where(Conversation.user_id == user_id)
            .where(Conversation.application_id == calling_application())
            .where(Conversation.dismissed_at.is_(None))
            .where(Conversation.site_id == site_id)
            .where(ConversationStrategy.is_saved.is_(True))
            .where(ConversationStrategy.wdk_strategy_id.is_not(None))
            .execution_options(populate_existing=True)
            .order_by(Conversation.name)
        )
        result = await self.session.execute(stmt)
        return paired(result.unique().all())

    async def get_by_wdk_strategy_id(
        self, user_id: UUID, wdk_strategy_id: int
    ) -> ConversationWithStrategy | None:
        result = await self.session.execute(
            with_strategy()
            .where(
                Conversation.user_id == user_id,
                Conversation.application_id == calling_application(),
                ConversationStrategy.wdk_strategy_id == wdk_strategy_id,
            )
            .execution_options(populate_existing=True)
        )
        rows = paired(result.all())
        return rows[0] if rows else None

    async def count_consumers_per_saved_strategy(
        self,
        user_id: UUID,
        site_id: str,
    ) -> dict[int, int]:
        """Return the consumer count for each saved WDK strategy id."""
        result = await self.session.execute(
            select(ConversationStrategy.imported_saved_strategy_ids)
            .join(
                Conversation,
                Conversation.id == ConversationStrategy.conversation_id,
            )
            .where(
                Conversation.user_id == user_id,
                Conversation.application_id == calling_application(),
                Conversation.site_id == site_id,
                Conversation.dismissed_at.is_(None),
            ),
        )
        counts: dict[int, int] = {}
        for (ids,) in result.all():
            for sid in ids or []:
                if isinstance(sid, int):
                    counts[sid] = counts.get(sid, 0) + 1
        return counts

    async def list_consumers_of_saved_strategy(
        self,
        user_id: UUID,
        wdk_strategy_id: int,
        *,
        exclude_conversation_id: UUID | None = None,
    ) -> list[Conversation]:
        """Return conversations that import the given saved WDK strategy. A
        strategy with consumers cannot be hard-deleted."""
        stmt = (
            select(Conversation)
            .join(
                ConversationStrategy,
                ConversationStrategy.conversation_id == Conversation.id,
            )
            .where(
                Conversation.user_id == user_id,
                Conversation.application_id == calling_application(),
                ConversationStrategy.imported_saved_strategy_ids.contains(
                    [wdk_strategy_id],
                ),
            )
        )
        if exclude_conversation_id is not None:
            stmt = stmt.where(Conversation.id != exclude_conversation_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
