from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ConversationAnalysis, ConversationStrategy

__all__ = ["a_binding_names", "a_projection_names"]


async def a_projection_names(session: AsyncSession, wdk_strategy_id: int) -> bool:
    found = await session.scalar(
        select(ConversationStrategy.conversation_id)
        .where(ConversationStrategy.wdk_strategy_id == wdk_strategy_id)
        .limit(1),
    )
    return found is not None


async def a_binding_names(session: AsyncSession, analysis_id: str) -> bool:
    found = await session.scalar(
        select(ConversationAnalysis.conversation_id)
        .where(ConversationAnalysis.analysis_id == analysis_id)
        .limit(1),
    )
    return found is not None
