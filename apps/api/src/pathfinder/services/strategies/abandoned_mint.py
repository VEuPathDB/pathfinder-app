"""Deleting on VEuPathDB a strategy PathFinder minted and no longer names."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.logging import get_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import get_strategy_api

from pathfinder.persistence.models import (
    ConversationStrategy,
    ConversationStrategyView,
    GeneSetRow,
    StrategyRevision,
)
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.services.conversations.strategy_ops import (
    list_saved_strategy_consumers,
)

logger = get_logger(__name__)

__all__ = ["ReleasableMint", "abandoned_mint_to_release", "delete_released_mint"]


@dataclass(frozen=True)
class ReleasableMint:
    """A minted VEuPathDB strategy nothing names any more."""

    conversation_id: UUID
    site_id: str
    wdk_strategy_id: int


async def _reference_to(
    session: AsyncSession,
    *,
    thread: Conversation,
    wdk_strategy_id: int,
) -> str | None:
    """The kind of row that still names the strategy, or None when none does.

    Four lookups: the user's gene sets under the thread's application, the
    thread's surviving snapshots, the strategy projections, and the other
    threads that hold the strategy as a saved input. The third one reads at
    most one row, because ``wdk_strategy_id`` is uniquely indexed where it is
    set.
    """
    gene_set = await session.scalar(
        select(GeneSetRow.id)
        .where(
            GeneSetRow.wdk_strategy_id == wdk_strategy_id,
            GeneSetRow.user_id == thread.user_id,
            GeneSetRow.application_id == thread.application_id,
        )
        .limit(1),
    )
    if gene_set is not None:
        return "gene_set"
    snapshot = await session.scalar(
        select(StrategyRevision.id)
        .where(
            StrategyRevision.conversation_id == thread.id,
            StrategyRevision.wdk_strategy_id == wdk_strategy_id,
        )
        .limit(1),
    )
    if snapshot is not None:
        return "strategy_revision"
    projection = await session.scalar(
        select(ConversationStrategy.conversation_id)
        .where(ConversationStrategy.wdk_strategy_id == wdk_strategy_id)
        .limit(1),
    )
    if projection is not None:
        return "conversation_strategy"
    consumers = await list_saved_strategy_consumers(
        ConversationRepository(session),
        thread.user_id,
        wdk_strategy_id,
        exclude_conversation_id=thread.id,
    )
    return "imported_saved_input" if consumers else None


async def abandoned_mint_to_release(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    abandoned: ConversationStrategyView,
    restored_wdk_strategy_id: int | None,
) -> ReleasableMint | None:
    """The VEuPathDB strategy a thread has just moved away from, or None.

    ``abandoned`` is the strategy projection as it stood before the move.
    A strategy is releasable only when PathFinder minted it, the thread now
    holds a different one, the user has not saved it, and no gene set,
    snapshot, projection or saved input of another thread still names it.
    The caller commits its own writes and then runs the delete.
    """
    mint = abandoned.wdk_strategy_id
    if mint is None or not abandoned.wdk_strategy_created_here:
        return None
    if mint == restored_wdk_strategy_id:
        return None
    if abandoned.is_saved:
        logger.debug(
            "Abandoned WDK strategy kept: the user saved it",
            conversation_id=str(conversation_id),
            wdk_strategy_id=mint,
        )
        return None
    thread = await session.get(Conversation, conversation_id)
    if thread is None:
        return None
    held_by = await _reference_to(session, thread=thread, wdk_strategy_id=mint)
    if held_by is not None:
        logger.debug(
            "Abandoned WDK strategy kept: a row still names it",
            conversation_id=str(conversation_id),
            wdk_strategy_id=mint,
            named_by=held_by,
        )
        return None
    return ReleasableMint(
        conversation_id=conversation_id,
        site_id=thread.site_id,
        wdk_strategy_id=mint,
    )


async def delete_released_mint(release: ReleasableMint | None) -> None:
    """Delete on VEuPathDB a mint the committed rows no longer name.

    VEuPathDB holds the saved mark, so the site answers it first. The strategy
    stays when the site reports it saved and when the site does not answer. A
    site that refuses the delete keeps it too, and does not fail the caller.
    """
    if release is None:
        return
    api = get_strategy_api(release.site_id)
    try:
        held = await api.get_strategy(release.wdk_strategy_id)
    except (VEuPathDBError, OSError, RuntimeError) as exc:
        logger.warning(
            "Abandoned WDK strategy kept: the site did not answer the saved mark",
            conversation_id=str(release.conversation_id),
            wdk_strategy_id=release.wdk_strategy_id,
            site=release.site_id,
            error=str(exc),
        )
        return
    if held.is_saved:
        logger.debug(
            "Abandoned WDK strategy kept: the site holds it as saved",
            conversation_id=str(release.conversation_id),
            wdk_strategy_id=release.wdk_strategy_id,
            site=release.site_id,
        )
        return
    try:
        await api.delete_strategy(release.wdk_strategy_id)
    except (VEuPathDBError, OSError, RuntimeError) as exc:
        logger.warning(
            "Failed to delete the WDK strategy an abandoned turn minted",
            conversation_id=str(release.conversation_id),
            wdk_strategy_id=release.wdk_strategy_id,
            site=release.site_id,
            error=str(exc),
        )
        return
    logger.info(
        "Deleted the WDK strategy an abandoned turn minted",
        conversation_id=str(release.conversation_id),
        wdk_strategy_id=release.wdk_strategy_id,
        site=release.site_id,
    )
