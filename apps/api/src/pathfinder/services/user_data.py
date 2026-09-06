"""Purges user data from the database and the in-memory caches, and optionally
from WDK."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import calling_application
from assistant_core.platform.logging import get_logger
from sqlalchemy import CursorResult, Row, Select, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk.factory import get_strategy_api

from pathfinder.persistence.models import (
    ControlSet,
    ConversationStrategy,
    ExperimentRow,
    GeneSetRow,
)
from pathfinder.persistence.repositories.eval_staging import delete_staged_for_user
from pathfinder.platform.errors import AppError
from pathfinder.services.conversations.cancellation import stop_turns_and_wait
from pathfinder.services.gene_sets.store import get_gene_set_store

logger = get_logger(__name__)


@dataclass(frozen=True)
class PurgeResult:
    """Summary of a user data purge operation."""

    hard_deleted: int
    dismissed: int
    wdk_strategies: int
    gene_sets: int
    experiments: int
    control_sets: int
    staged_eval_cases: int


async def purge_user_data(
    *,
    session: AsyncSession,
    user_id: UUID,
    site_id: str | None,
    delete_wdk: bool,
) -> PurgeResult:
    """Purge the calling application's data for one user, from all local stores.

    Without ``delete_wdk``, chats are dismissed rather than deleted, so WDK
    sync does not re-import them. With ``delete_wdk``, chats are deleted, and
    so are the WDK strategies those chats built. Gene sets, experiments, and
    control sets are always deleted. A caller destroys only what it can read,
    so the same user's data under another application is untouched.
    """
    application_id = calling_application()
    # The outer join makes the strategy row nullable, which the select type
    # of the three entities does not express.
    selected: Select[tuple[UUID, str, ConversationStrategy | None]] = select(
        Conversation.id,
        Conversation.site_id,
        ConversationStrategy,
    )
    conversation_query = selected.outerjoin(
        ConversationStrategy,
        ConversationStrategy.conversation_id == Conversation.id,
    ).where(
        Conversation.user_id == user_id,
        Conversation.application_id == application_id,
    )
    if site_id:
        conversation_query = conversation_query.where(Conversation.site_id == site_id)
    conversations = list((await session.execute(conversation_query)).all())
    conversation_ids = [row.id for row in conversations]

    still_running = await stop_turns_and_wait(conversation_ids)
    if still_running:
        logger.warning(
            "Purging threads whose turn has not stopped",
            user_id=str(user_id),
            conversations=[str(conversation_id) for conversation_id in still_running],
        )

    wdk_deleted = await _purge_wdk_strategies(
        _strategies_built_by(conversations),
        delete_wdk=delete_wdk,
    )

    dismissed_count = 0
    hard_deleted_count = 0

    if delete_wdk:
        conv_del = delete(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.application_id == application_id,
        )
        if site_id:
            conv_del = conv_del.where(Conversation.site_id == site_id)
        sr = cast("CursorResult[object]", await session.execute(conv_del))
        hard_deleted_count = sr.rowcount or 0
    elif conversation_ids:
        await session.execute(
            update(Conversation)
            .where(Conversation.id.in_(conversation_ids))
            .values(dismissed_at=datetime.now(UTC))
        )
        dismissed_count = len(conversation_ids)

    pg_gene_sets, pg_experiments, pg_control_sets = await _purge_related_data(
        session, user_id, site_id
    )
    # A staged eval candidate is still the user's; a promoted case names
    # nobody and is out of reach here.
    staged_eval_cases = await delete_staged_for_user(session, user_id=user_id)

    await session.commit()

    _clear_gene_set_cache(user_id, site_id)

    strategies_handled = hard_deleted_count + dismissed_count
    logger.info(
        "Purged user data",
        user_id=str(user_id),
        site_id=site_id,
        delete_wdk=delete_wdk,
        strategies=strategies_handled,
        wdk_strategies=wdk_deleted,
        gene_sets=pg_gene_sets,
        experiments=pg_experiments,
        control_sets=pg_control_sets,
        staged_eval_cases=staged_eval_cases,
    )

    return PurgeResult(
        hard_deleted=hard_deleted_count,
        dismissed=dismissed_count,
        wdk_strategies=wdk_deleted,
        gene_sets=pg_gene_sets,
        experiments=pg_experiments,
        control_sets=pg_control_sets,
        staged_eval_cases=staged_eval_cases,
    )


def _strategies_built_by(
    conversations: Sequence[Row[tuple[UUID, str, ConversationStrategy | None]]],
) -> dict[str, set[int]]:
    """Group by site the WDK strategies these conversations built.

    A saved strategy a conversation only imported is left out: the user can
    have made it on the website, and another conversation can still consume it.
    """
    by_site: dict[str, set[int]] = {}
    for _id, row_site_id, strategy in conversations:
        if strategy is None or strategy.wdk_strategy_id is None:
            continue
        by_site.setdefault(row_site_id, set()).add(strategy.wdk_strategy_id)
    return by_site


async def _purge_wdk_strategies(
    built: dict[str, set[int]],
    *,
    delete_wdk: bool,
) -> int:
    """Delete the WDK strategies the purged conversations built, and no others.

    A site PathFinder cannot reach, or cannot act on because the request names
    no registered VEuPathDB user, is skipped so the local purge still runs.
    """
    if not delete_wdk:
        return 0

    # Deletes run concurrently. A sequential loop over every site exceeds the
    # upstream connection idle timeout.
    semaphore = asyncio.Semaphore(10)
    wdk_deleted = 0
    for purge_site, wanted in built.items():
        try:
            api = get_strategy_api(purge_site)
            live = {s.strategy_id for s in await api.list_strategies()}
        except (AppError, VEuPathDBError, OSError, RuntimeError) as exc:
            logger.debug("WDK purge skipped for site", site=purge_site, error=str(exc))
            continue

        async def _delete_one(strategy_id: int, *, site: str = purge_site) -> int:
            async with semaphore:
                try:
                    await get_strategy_api(site).delete_strategy(strategy_id)
                except (AppError, VEuPathDBError, OSError, RuntimeError) as exc:
                    logger.warning(
                        "Failed to delete WDK strategy during user data purge",
                        wdk_strategy_id=strategy_id,
                        site=site,
                        error=str(exc),
                    )
                    return 0
                return 1

        outcomes = await asyncio.gather(
            *(_delete_one(strategy_id) for strategy_id in sorted(wanted & live))
        )
        wdk_deleted += sum(outcomes)
    return wdk_deleted


async def _purge_related_data(
    session: AsyncSession,
    user_id: UUID,
    site_id: str | None,
) -> tuple[int, int, int]:
    """Delete the calling application's gene sets, experiments and control sets."""
    application_id = calling_application()
    gs_del = delete(GeneSetRow).where(
        GeneSetRow.user_id == user_id,
        GeneSetRow.application_id == application_id,
    )
    if site_id:
        gs_del = gs_del.where(GeneSetRow.site_id == site_id)
    gr = cast("CursorResult[object]", await session.execute(gs_del))
    pg_gene_sets = gr.rowcount or 0

    exp_del = delete(ExperimentRow).where(
        ExperimentRow.user_id == user_id,
        ExperimentRow.application_id == application_id,
    )
    if site_id:
        exp_del = exp_del.where(ExperimentRow.site_id == site_id)
    er = cast("CursorResult[object]", await session.execute(exp_del))
    pg_experiments = er.rowcount or 0

    cs_del = delete(ControlSet).where(
        ControlSet.user_id == user_id,
        ControlSet.application_id == application_id,
    )
    if site_id:
        cs_del = cs_del.where(ControlSet.site_id == site_id)
    cr = cast("CursorResult[object]", await session.execute(cs_del))
    pg_control_sets = cr.rowcount or 0

    return pg_gene_sets, pg_experiments, pg_control_sets


def _clear_gene_set_cache(user_id: UUID, site_id: str | None) -> None:
    """Clear the calling application's in-memory gene set cache entries."""
    application_id = calling_application()
    try:
        cache = get_gene_set_store()
        to_evict = [
            gid
            for gid, gs in cache._cache.items()
            if gs.user_id == user_id
            and gs.application_id == application_id
            and (site_id is None or gs.site_id == site_id)
        ]
        for gid in to_evict:
            cache._cache.pop(gid, None)
    except (RuntimeError, KeyError) as exc:
        logger.warning(
            "Failed to clear gene set cache during user data purge",
            user_id=str(user_id),
            error=str(exc),
        )
