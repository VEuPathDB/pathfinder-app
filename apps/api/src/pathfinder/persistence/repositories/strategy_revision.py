"""The append log of a thread's strategy, and the reads fork and revert need."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.strategy.revision import (
    parse_strategy_ast,
    strategy_revision_of_raw,
    without_wdk_ids,
)
from pathfinder.persistence.models import (
    ConversationStrategyView,
    StrategyRevision,
    StrategyRevisionView,
)

__all__ = ["StrategyRevisionRepository"]


def _rows(result: object) -> int:
    return cast("CursorResult[object]", result).rowcount or 0


class StrategyRevisionRepository:
    """Append and read the strategy snapshots of one thread."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        conversation_id: UUID,
        strategy: ConversationStrategyView,
        *,
        message_id: UUID | None = None,
    ) -> StrategyRevisionView | None:
        """Append the strategy's current state. A repeat of the newest row is
        not appended twice."""
        revision = strategy_revision_of_raw(strategy.strategy_ast)
        ast = parse_strategy_ast(strategy.strategy_ast)
        latest = await self.latest(conversation_id)
        if (
            latest is not None
            and latest.revision == revision
            and latest.wdk_strategy_id == strategy.wdk_strategy_id
            and latest.wdk_strategy_created_here == strategy.wdk_strategy_created_here
            and latest.is_saved == strategy.is_saved
            and latest.step_count == strategy.step_count
        ):
            return latest
        row = StrategyRevision(
            conversation_id=conversation_id,
            revision=revision,
            record_type=strategy.record_type,
            strategy_ast=dict(strategy.strategy_ast),
            step_count=strategy.step_count,
            wdk_strategy_id=strategy.wdk_strategy_id,
            wdk_strategy_created_here=strategy.wdk_strategy_created_here,
            is_saved=strategy.is_saved,
            name=ast.name if ast is not None else None,
            message_id=message_id,
        )
        self.session.add(row)
        await self.session.flush()
        return StrategyRevisionView.model_validate(row)

    async def name_latest(
        self,
        conversation_id: UUID,
        *,
        message_id: UUID,
    ) -> None:
        """Record which message the thread's newest snapshot belongs to."""
        newest = await self.session.scalar(
            select(StrategyRevision.id)
            .where(StrategyRevision.conversation_id == conversation_id)
            .order_by(desc(StrategyRevision.id))
            .limit(1),
        )
        if newest is None:
            return
        await self.session.execute(
            update(StrategyRevision)
            .where(StrategyRevision.id == newest)
            .values(message_id=message_id),
        )

    async def named_by(
        self,
        conversation_id: UUID,
        *,
        message_id: UUID,
    ) -> StrategyRevisionView | None:
        row = await self.session.scalar(
            select(StrategyRevision)
            .where(
                StrategyRevision.conversation_id == conversation_id,
                StrategyRevision.message_id == message_id,
            )
            .order_by(desc(StrategyRevision.id))
            .limit(1),
        )
        return None if row is None else StrategyRevisionView.model_validate(row)

    async def latest(self, conversation_id: UUID) -> StrategyRevisionView | None:
        row = await self.session.scalar(
            select(StrategyRevision)
            .where(StrategyRevision.conversation_id == conversation_id)
            .order_by(desc(StrategyRevision.id))
            .limit(1),
        )
        return None if row is None else StrategyRevisionView.model_validate(row)

    async def newest(
        self,
        conversation_id: UUID,
        *,
        limit: int,
    ) -> list[StrategyRevisionView]:
        """The thread's most recent snapshots, newest first."""
        rows = await self.session.scalars(
            select(StrategyRevision)
            .where(StrategyRevision.conversation_id == conversation_id)
            .order_by(desc(StrategyRevision.id))
            .limit(limit),
        )
        return [StrategyRevisionView.model_validate(row) for row in rows]

    async def at_or_before(
        self,
        conversation_id: UUID,
        moment: datetime,
    ) -> StrategyRevisionView | None:
        """The newest snapshot written no later than ``moment``."""
        row = await self.session.scalar(
            select(StrategyRevision)
            .where(
                StrategyRevision.conversation_id == conversation_id,
                StrategyRevision.created_at <= moment,
            )
            .order_by(desc(StrategyRevision.created_at), desc(StrategyRevision.id))
            .limit(1),
        )
        return None if row is None else StrategyRevisionView.model_validate(row)

    async def has_any(self, conversation_id: UUID) -> bool:
        found = await self.session.scalar(
            select(StrategyRevision.id)
            .where(StrategyRevision.conversation_id == conversation_id)
            .limit(1),
        )
        return found is not None

    async def delete_newer_than(
        self,
        conversation_id: UUID,
        *,
        revision_row_id: int | None,
    ) -> int:
        """Drop the snapshots a truncation disowns. ``None`` drops them all."""
        stmt = delete(StrategyRevision).where(
            StrategyRevision.conversation_id == conversation_id,
        )
        if revision_row_id is not None:
            stmt = stmt.where(StrategyRevision.id > revision_row_id)
        return _rows(await self.session.execute(stmt))

    async def delete_at_or_after(
        self,
        conversation_id: UUID,
        *,
        moment: datetime,
    ) -> int:
        return _rows(
            await self.session.execute(
                delete(StrategyRevision).where(
                    StrategyRevision.conversation_id == conversation_id,
                    StrategyRevision.created_at >= moment,
                ),
            ),
        )

    async def copy_prefix(
        self,
        *,
        source_conversation_id: UUID,
        target_conversation_id: UUID,
        cutoff: datetime | None,
        message_id_map: dict[str, str],
    ) -> None:
        """Copy the snapshots a fork's prefix produced, under the fork's ids.

        A fork never owned the WDK strategy of its source, so the copies keep
        the plan and drop every WDK id.
        """
        stmt = select(StrategyRevision).where(
            StrategyRevision.conversation_id == source_conversation_id,
        )
        if cutoff is not None:
            stmt = stmt.where(StrategyRevision.created_at < cutoff)
        rows = (
            (await self.session.execute(stmt.order_by(StrategyRevision.id)))
            .scalars()
            .all()
        )
        for src in rows:
            mapped = (
                message_id_map.get(str(src.message_id))
                if src.message_id is not None
                else None
            )
            self.session.add(
                StrategyRevision(
                    conversation_id=target_conversation_id,
                    revision=src.revision,
                    record_type=src.record_type,
                    strategy_ast=without_wdk_ids(src.strategy_ast),
                    step_count=src.step_count,
                    wdk_strategy_id=None,
                    wdk_strategy_created_here=False,
                    is_saved=False,
                    name=src.name,
                    message_id=UUID(mapped) if mapped is not None else None,
                    created_at=src.created_at,
                ),
            )
        await self.session.flush()
