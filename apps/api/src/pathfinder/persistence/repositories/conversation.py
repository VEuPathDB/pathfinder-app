"""Data access for chat conversations: identity, strategy projection, and the
conversation sidebar."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories import conversation
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ConversationStrategy, ConversationStrategyView
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
    strategy_view_of,
)
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
    collect_strategy_values,
)
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)


class ConversationRepository:
    """The thread store, plus the strategy projection this application keeps.

    The thread's own columns belong to the runtime's repository; every method
    here either reads the projection beside them or writes it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._threads = conversation.ConversationRepository(session)

    async def create(
        self,
        user_id: UUID,
        site_id: str,
        *,
        assistant_id: str,
        conversation_id: UUID | None = None,
        name: str = "",
    ) -> Conversation:
        """Create a thread that names the assistant answering it.

        A caller can supply the id so the client and the server use one value.
        """
        created = await self._threads.create(
            user_id,
            site_id,
            conversation_id=conversation_id,
            name=name,
        )
        created.assistant_id = assistant_id
        await self.session.flush()
        return created

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        return await self._threads.get_by_id(conversation_id)

    async def get_strategy(self, conversation_id: UUID) -> ConversationStrategyView:
        """The thread's strategy projection; all-default when it has none."""
        result = await self.session.execute(
            select(ConversationStrategy)
            .where(ConversationStrategy.conversation_id == conversation_id)
            .execution_options(populate_existing=True)
        )
        return strategy_view_of(result.scalar_one_or_none())

    async def _projections(
        self,
        conversation_ids: list[UUID],
    ) -> dict[UUID, ConversationStrategy]:
        """The strategy rows of these threads, keyed by thread."""
        if not conversation_ids:
            return {}
        rows = await self.session.execute(
            select(ConversationStrategy)
            .where(ConversationStrategy.conversation_id.in_(conversation_ids))
            .execution_options(populate_existing=True)
        )
        return {row.conversation_id: row for row in rows.scalars().all()}

    async def _paired(
        self,
        threads: list[Conversation],
    ) -> list[ConversationWithStrategy]:
        projections = await self._projections([thread.id for thread in threads])
        return [
            (thread, strategy_view_of(projections.get(thread.id))) for thread in threads
        ]

    async def get_with_strategy(
        self, conversation_id: UUID
    ) -> ConversationWithStrategy | None:
        """The thread beside its strategy projection, or None when it is gone."""
        thread = await self._threads.get_by_id(conversation_id)
        if thread is None:
            return None
        return (thread, await self.get_strategy(conversation_id))

    async def delete(
        self,
        conversation_id: UUID,
        *,
        cascade: bool = False,
    ) -> None:
        """Delete a conversation.

        Without ``cascade`` the direct children move up to the deleted node's
        parent. With ``cascade`` the whole subtree goes.
        """
        await self._threads.delete(conversation_id, cascade=cascade)

    async def list_conversations(
        self,
        user_id: UUID,
        site_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationWithStrategy]:
        """List chats that are not dismissed, most recently updated first."""
        threads = await self._threads.list_active(
            user_id,
            site_id=site_id,
            limit=limit,
        )
        return await self._paired(threads)

    async def list_dismissed_conversations(
        self,
        user_id: UUID,
        site_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationWithStrategy]:
        threads = await self._threads.list_dismissed(
            user_id,
            site_id=site_id,
            limit=limit,
        )
        return await self._paired(threads)

    async def update_conversation(
        self, conversation_id: UUID, upd: ConversationUpdate
    ) -> None:
        """Update chat metadata from the fields present in the payload."""
        stored_name = await self._threads.update_thread(
            conversation_id,
            name=upd.name,
            touch_updated_at=upd.touch_updated_at,
        )
        if stored_name is not None:
            upd.name = stored_name
        await self._write_strategy(conversation_id, collect_strategy_values(upd))
        await self.session.flush()

    async def _write_strategy(
        self,
        conversation_id: UUID,
        values: dict[str, Any],
    ) -> None:
        """Create or update the strategy projection of an existing thread.

        A thread that is already gone takes no strategy row, so a write that
        lost a race with a delete is dropped instead of failing the caller.
        """
        if not values:
            return
        if await self._threads.get_by_id(conversation_id) is None:
            return
        await self.session.execute(
            insert(ConversationStrategy)
            .values(conversation_id=conversation_id, **values)
            .on_conflict_do_update(
                index_elements=[ConversationStrategy.conversation_id],
                set_=values,
            ),
        )
        await self._record_revision(conversation_id)

    async def _record_revision(self, conversation_id: UUID) -> None:
        """Append the resulting state to the thread's revision history."""
        await StrategyRevisionRepository(self.session).record(
            conversation_id,
            await self.get_strategy(conversation_id),
        )

    async def clear_strategy(self, conversation_id: UUID) -> None:
        """Blank the built strategy, keeping the thread's other links.

        A thread that never had a strategy has nothing to clear.
        """
        await self._threads.update_thread(conversation_id, touch_updated_at=True)
        await self.session.execute(
            update(ConversationStrategy)
            .where(ConversationStrategy.conversation_id == conversation_id)
            .values(
                strategy_ast={},
                record_type=None,
                wdk_strategy_id=None,
                wdk_strategy_created_here=False,
                is_saved=False,
                step_count=0,
                estimated_size=None,
            )
        )
        await self._record_revision(conversation_id)
        await self.session.flush()

    async def dismiss(self, conversation_id: UUID) -> None:
        """Mark a chat as dismissed, which hides it from the main list."""
        await self._threads.dismiss(conversation_id)

    async def restore(self, conversation_id: UUID) -> None:
        """Restore a dismissed chat and clear its strategy AST."""
        await self._threads.restore(conversation_id)
        await self.session.execute(
            update(ConversationStrategy)
            .where(ConversationStrategy.conversation_id == conversation_id)
            .values(strategy_ast={})
        )
        await self._record_revision(conversation_id)
        await self.session.flush()
