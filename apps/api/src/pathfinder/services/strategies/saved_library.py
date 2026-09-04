"""Reads the caller's saved strategies, by name, by WDK id or by thread id."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.db import DBSessionFactory
from assistant_core.platform.pydantic_base import CamelModel

from pathfinder.persistence.repositories.saved_strategy import (
    SavedStrategyRepository,
)


class SavedStrategyListing(CamelModel):
    """One saved strategy the user can reuse as the input of a new one."""

    conversation_id: str
    name: str
    wdk_strategy_id: int
    record_type: str
    root_count: int | None = None
    step_count: int = 0


async def list_saved_strategies(
    db_session_factory: DBSessionFactory,
    *,
    user_id: UUID,
    site_id: str,
) -> list[SavedStrategyListing]:
    """The saved strategies the user owns on the site, ordered by name."""
    async with db_session_factory() as session:
        rows = await SavedStrategyRepository(session).list_saved_strategies(
            user_id, site_id
        )
    return [
        SavedStrategyListing(
            conversation_id=str(conversation.id),
            name=conversation.name,
            wdk_strategy_id=strategy.wdk_strategy_id or 0,
            record_type=strategy.record_type or "",
            root_count=strategy.estimated_size,
            step_count=strategy.step_count,
        )
        for conversation, strategy in rows
    ]


def match_saved_reference(
    listing: list[SavedStrategyListing], reference: str
) -> SavedStrategyListing | None:
    """Find the one entry a reference names: a thread id, a WDK id, or a name."""
    wanted = reference.strip()
    if not wanted:
        return None
    folded = wanted.casefold()
    for entry in listing:
        if wanted in (entry.conversation_id, str(entry.wdk_strategy_id)):
            return entry
        if entry.name.casefold() == folded:
            return entry
    partial = [e for e in listing if folded in e.name.casefold()]
    if len(partial) == 1:
        return partial[0]
    return None
