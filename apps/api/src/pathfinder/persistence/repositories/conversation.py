"""Data access for chat conversations: identity, strategy projection, and the
conversation sidebar."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import calling_application
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.conversation import DEFAULT_STREAM_NAME
from pathfinder.persistence.models import ConversationStrategy, ConversationStrategyView
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
    paired,
    strategy_view_of,
    with_strategy,
)
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
    collect_strategy_values,
)
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)


class ConversationRepository:
    """Data access for chat conversations.

    Every listing is scoped to the user under the calling application; a
    lookup by id is not, because the ownership helpers decide that case.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _deduplicate_name(
        self,
        user_id: UUID,
        site_id: str,
        name: str,
        exclude_conversation_id: UUID | None = None,
    ) -> str:
        """Return a unique chat name for the user and site. A taken name gets
        a numeric suffix."""
        query = select(Conversation.name).where(
            Conversation.user_id == user_id,
            Conversation.application_id == calling_application(),
            Conversation.site_id == site_id,
        )
        if exclude_conversation_id is not None:
            query = query.where(Conversation.id != exclude_conversation_id)
        result = await self.session.execute(query)
        existing: set[str] = {row[0] for row in result.all() if row[0]}

        if name not in existing:
            return name

        i = 1
        while f"{name} ({i})" in existing:
            i += 1
        return f"{name} ({i})"

    async def create(
        self,
        user_id: UUID,
        site_id: str,
        *,
        conversation_id: UUID | None = None,
        name: str = "",
    ) -> Conversation:
        """Create a chat with a deduplicated name. Callers can supply the id so
        the client and the server use the same value."""
        resolved_name = await self._deduplicate_name(
            user_id,
            site_id,
            name or DEFAULT_STREAM_NAME,
        )
        conversation = Conversation(
            id=conversation_id or uuid4(),
            user_id=user_id,
            site_id=site_id,
            name=resolved_name,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_strategy(self, conversation_id: UUID) -> ConversationStrategyView:
        """The thread's strategy projection; all-default when it has none."""
        result = await self.session.execute(
            select(ConversationStrategy)
            .where(ConversationStrategy.conversation_id == conversation_id)
            .execution_options(populate_existing=True)
        )
        return strategy_view_of(result.scalar_one_or_none())

    async def get_with_strategy(
        self, conversation_id: UUID
    ) -> ConversationWithStrategy | None:
        result = await self.session.execute(
            with_strategy()
            .where(Conversation.id == conversation_id)
            .execution_options(populate_existing=True)
        )
        rows = paired(result.all())
        return rows[0] if rows else None

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
        if cascade:
            sql = text(
                """
                WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM conversations WHERE id = :id
                    UNION ALL
                    SELECT c.id FROM conversations c
                    JOIN descendants d ON c.parent_conversation_id = d.id
                )
                DELETE FROM conversations WHERE id IN (SELECT id FROM descendants)
                """,
            )
            await self.session.execute(sql, {"id": str(conversation_id)})
            await self.session.flush()
            return

        deleted = await self.session.scalar(
            select(Conversation).where(Conversation.id == conversation_id),
        )
        if deleted is not None:
            await self.session.execute(
                update(Conversation)
                .where(Conversation.parent_conversation_id == conversation_id)
                .values(
                    parent_conversation_id=deleted.parent_conversation_id,
                    parent_message_id=deleted.parent_message_id,
                ),
            )
        await self.session.execute(
            delete(Conversation).where(Conversation.id == conversation_id),
        )
        await self.session.flush()

    async def list_conversations(
        self,
        user_id: UUID,
        site_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationWithStrategy]:
        """List chats that are not dismissed, most recently updated first."""
        stmt = (
            with_strategy()
            .where(Conversation.user_id == user_id)
            .where(Conversation.application_id == calling_application())
            .where(Conversation.dismissed_at.is_(None))
            .execution_options(populate_existing=True)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        if site_id:
            stmt = stmt.where(Conversation.site_id == site_id)
        result = await self.session.execute(stmt)
        return paired(result.unique().all())

    async def list_dismissed_conversations(
        self,
        user_id: UUID,
        site_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationWithStrategy]:
        stmt = (
            with_strategy()
            .where(Conversation.user_id == user_id)
            .where(Conversation.application_id == calling_application())
            .where(Conversation.dismissed_at.is_not(None))
            .execution_options(populate_existing=True)
            .order_by(Conversation.dismissed_at.desc())
            .limit(limit)
        )
        if site_id:
            stmt = stmt.where(Conversation.site_id == site_id)
        result = await self.session.execute(stmt)
        return paired(result.unique().all())

    async def update_conversation(
        self, conversation_id: UUID, upd: ConversationUpdate
    ) -> None:
        """Update chat metadata from the fields present in the payload."""
        thread_values: dict[str, Any] = {}
        if upd.touch_updated_at:
            thread_values["updated_at"] = datetime.now(UTC)
        if upd.name is not None:
            owner = (
                await self.session.execute(
                    select(Conversation.user_id, Conversation.site_id).where(
                        Conversation.id == conversation_id,
                    ),
                )
            ).one_or_none()
            if owner is not None:
                upd.name = await self._deduplicate_name(
                    owner.user_id,
                    owner.site_id,
                    upd.name,
                    exclude_conversation_id=conversation_id,
                )
            thread_values["name"] = upd.name

        if thread_values:
            await self.session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(**thread_values)
            )

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
        thread = await self.session.scalar(
            select(Conversation.id).where(Conversation.id == conversation_id),
        )
        if thread is None:
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
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=datetime.now(UTC))
        )
        await self.session.execute(
            update(ConversationStrategy)
            .where(ConversationStrategy.conversation_id == conversation_id)
            .values(
                strategy_ast={},
                record_type=None,
                wdk_strategy_id=None,
                step_count=0,
                estimated_size=None,
            )
        )
        await self._record_revision(conversation_id)
        await self.session.flush()

    async def dismiss(self, conversation_id: UUID) -> None:
        """Mark a chat as dismissed, which hides it from the main list."""
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(dismissed_at=datetime.now(UTC))
        )
        await self.session.flush()

    async def restore(self, conversation_id: UUID) -> None:
        """Restore a dismissed chat and clear its strategy AST."""
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(dismissed_at=None)
        )
        await self.session.execute(
            update(ConversationStrategy)
            .where(ConversationStrategy.conversation_id == conversation_id)
            .values(strategy_ast={})
        )
        await self._record_revision(conversation_id)
        await self.session.flush()
