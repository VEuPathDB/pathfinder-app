"""Purges user data from the database and the in-memory caches, and optionally
from WDK."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from assistant_core.conversation.cancellation import stop_turns_and_wait
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation, MemoryTombstoneRow
from assistant_core.platform.context import calling_application
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from sqlalchemy import CursorResult, Row, Select, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import get_strategy_api

from pathfinder.domain.memory import MEMORY_KINDS, MemoryKind
from pathfinder.persistence.models import (
    ControlSet,
    ConversationStrategy,
    ExperimentRow,
    GeneSetRow,
)
from pathfinder.persistence.repositories.eval_staging import delete_staged_for_user
from pathfinder.services.gene_sets.store import get_gene_set_store

logger = get_logger(__name__)

_MEMORY_PAGE = 200


@dataclass(frozen=True)
class PurgeResult:
    """Summary of a user data purge operation."""

    hard_deleted: int
    dismissed: int
    wdk_strategies: int
    wdk_strategies_kept: int
    memories: int
    gene_sets: int
    experiments: int
    control_sets: int
    staged_eval_cases: int


@dataclass(frozen=True)
class WdkPurgeOutcome:
    """Which of the wanted strategies VEuPathDB accepted the deletion of.

    Each member is a ``(site, strategy id)`` pair.
    """

    deleted: frozenset[tuple[str, int]]
    kept: frozenset[tuple[str, int]]


async def purge_user_data(
    *,
    session: AsyncSession,
    user_id: UUID,
    site_id: str | None,
    delete_wdk: bool,
    memory_store: MemoryStore,
) -> PurgeResult:
    """Purge the calling application's data for one user, from all local stores.

    Without ``delete_wdk``, chats are dismissed rather than deleted, so WDK
    sync does not re-import them. With ``delete_wdk``, chats are deleted, and
    so are the VEuPathDB strategies PathFinder created for them. A strategy
    the user made on the website stays. A chat whose VEuPathDB strategy is
    still there is dismissed instead of deleted, and a run in the same
    position keeps its row, so a later purge can finish the job. Gene sets,
    experiments, and control sets are otherwise deleted.
    A caller destroys only what it can read, so the same user's data under
    another application is untouched. A staged eval candidate names a site, so
    a purge of one site clears only that site's. A memory names no site, so
    only a purge of every site clears the memories and the tombstones that
    hold them out.
    The memories go after the relational purge commits, so a failure there
    raises with every memory still in place and the call can be repeated.
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

    runs = await _strategies_built_for_runs(session, user_id, site_id)
    outcome = await _purge_wdk_strategies(
        _by_site(_strategies_built_by(conversations), runs),
        delete_wdk=delete_wdk,
    )
    kept_conversations = _threads_still_on_the_site(conversations, outcome.kept)
    kept_runs = [
        run.experiment_id
        for run in runs
        if (run.site_id, run.wdk_strategy_id) in outcome.kept
    ]

    dismissed_count = 0
    hard_deleted_count = 0

    if delete_wdk:
        conv_del = delete(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.application_id == application_id,
        )
        if site_id:
            conv_del = conv_del.where(Conversation.site_id == site_id)
        if kept_conversations:
            conv_del = conv_del.where(Conversation.id.notin_(kept_conversations))
        sr = cast("CursorResult[object]", await session.execute(conv_del))
        hard_deleted_count = sr.rowcount or 0
    to_dismiss = kept_conversations if delete_wdk else conversation_ids
    if to_dismiss:
        await session.execute(
            update(Conversation)
            .where(Conversation.id.in_(to_dismiss))
            .values(dismissed_at=datetime.now(UTC))
        )
        dismissed_count = len(to_dismiss)

    pg_gene_sets, pg_experiments, pg_control_sets = await _purge_related_data(
        session, user_id, site_id, kept_runs
    )
    # A staged eval candidate is still the user's; a promoted case names
    # nobody and is out of reach here.
    staged_eval_cases = await delete_staged_for_user(
        session,
        user_id=user_id,
        application_id=application_id,
        site_id=site_id,
    )

    await session.commit()

    memories = 0 if site_id else await _purge_memories(memory_store, session, user_id)
    _clear_gene_set_cache(user_id, site_id)

    strategies_handled = hard_deleted_count + dismissed_count
    logger.info(
        "Purged user data",
        user_id=str(user_id),
        site_id=site_id,
        delete_wdk=delete_wdk,
        strategies=strategies_handled,
        wdk_strategies=len(outcome.deleted),
        wdk_strategies_kept=len(outcome.kept),
        memories=memories,
        gene_sets=pg_gene_sets,
        experiments=pg_experiments,
        control_sets=pg_control_sets,
        staged_eval_cases=staged_eval_cases,
    )

    return PurgeResult(
        hard_deleted=hard_deleted_count,
        dismissed=dismissed_count,
        wdk_strategies=len(outcome.deleted),
        wdk_strategies_kept=len(outcome.kept),
        memories=memories,
        gene_sets=pg_gene_sets,
        experiments=pg_experiments,
        control_sets=pg_control_sets,
        staged_eval_cases=staged_eval_cases,
    )


async def _memory_keys(
    store: MemoryStore,
    user_id: UUID,
    kind: MemoryKind,
) -> list[str]:
    """Every key one user holds of one kind."""
    keys: list[str] = []
    offset = 0
    while True:
        page = await store.list_all(
            user_id=user_id,
            kind=kind,
            limit=_MEMORY_PAGE,
            offset=offset,
        )
        keys.extend(stored.key for stored in page)
        if len(page) < _MEMORY_PAGE:
            return keys
        offset += _MEMORY_PAGE


async def _purge_memories(
    store: MemoryStore,
    session: AsyncSession,
    user_id: UUID,
) -> int:
    """Delete one user's memories, and the tombstones that hold them out.

    A tombstone left behind would keep a future memory of the same content
    from ever being written. A failure reaches the caller: the memories that
    remain are the ones a repeat of the purge deletes.
    """
    deleted = 0
    for kind in MEMORY_KINDS:
        keys = await _memory_keys(store, user_id, kind)
        for key in keys:
            await store.delete(user_id=user_id, kind=kind, key=key)
        deleted += len(keys)
    await session.execute(
        delete(MemoryTombstoneRow).where(
            MemoryTombstoneRow.user_id == user_id,
            MemoryTombstoneRow.application_id == calling_application(),
        ),
    )
    await session.commit()
    return deleted


def _strategies_built_by(
    conversations: Sequence[Row[tuple[UUID, str, ConversationStrategy | None]]],
) -> dict[str, set[int]]:
    """Group by site the WDK strategies PathFinder created for these conversations.

    A strategy the user made on the website and opened here is left out, and
    so is one whose row predates the record of who created it.
    """
    by_site: dict[str, set[int]] = {}
    for _id, row_site_id, strategy in conversations:
        if strategy is None or strategy.wdk_strategy_id is None:
            continue
        if not strategy.wdk_strategy_created_here:
            continue
        by_site.setdefault(row_site_id, set()).add(strategy.wdk_strategy_id)
    return by_site


class _StoredExperiment(CamelModel):
    """The VEuPathDB strategy one stored run created, read from its blob."""

    model_config = ConfigDict(extra="ignore")

    wdk_strategy_id: int | None = None


@dataclass(frozen=True)
class _RunStrategy:
    """One stored run and the VEuPathDB strategy it created."""

    experiment_id: str
    site_id: str
    wdk_strategy_id: int


async def _strategies_built_for_runs(
    session: AsyncSession,
    user_id: UUID,
    site_id: str | None,
) -> list[_RunStrategy]:
    """The strategies PathFinder created on VEuPathDB to persist a run.

    A run creates its strategy itself, so no conversation names it.
    """
    query = select(
        ExperimentRow.id,
        ExperimentRow.site_id,
        ExperimentRow.data,
    ).where(
        ExperimentRow.user_id == user_id,
        ExperimentRow.application_id == calling_application(),
    )
    if site_id:
        query = query.where(ExperimentRow.site_id == site_id)
    found: list[_RunStrategy] = []
    for experiment_id, row_site_id, data in (await session.execute(query)).all():
        stored = _StoredExperiment.model_validate(data)
        if stored.wdk_strategy_id is not None:
            found.append(
                _RunStrategy(
                    experiment_id=experiment_id,
                    site_id=row_site_id,
                    wdk_strategy_id=stored.wdk_strategy_id,
                ),
            )
    return found


def _by_site(
    from_conversations: dict[str, set[int]],
    from_runs: Sequence[_RunStrategy],
) -> dict[str, set[int]]:
    merged = {site: set(ids) for site, ids in from_conversations.items()}
    for run in from_runs:
        merged.setdefault(run.site_id, set()).add(run.wdk_strategy_id)
    return merged


def _threads_still_on_the_site(
    conversations: Sequence[Row[tuple[UUID, str, ConversationStrategy | None]]],
    kept: frozenset[tuple[str, int]],
) -> list[UUID]:
    """The threads whose VEuPathDB strategy the purge could not delete."""
    return [
        conversation_id
        for conversation_id, row_site_id, strategy in conversations
        if strategy is not None
        and strategy.wdk_strategy_id is not None
        and (row_site_id, strategy.wdk_strategy_id) in kept
    ]


async def _purge_wdk_strategies(
    built: dict[str, set[int]],
    *,
    delete_wdk: bool,
) -> WdkPurgeOutcome:
    """Delete on VEuPathDB the strategies PathFinder created there, and no others.

    A site PathFinder cannot reach, or cannot act on because the request names
    no registered VEuPathDB user, keeps every strategy it holds. A wanted
    strategy the site does not list is already gone.
    """
    if not delete_wdk:
        return WdkPurgeOutcome(frozenset(), frozenset())

    # Deletes run concurrently. A sequential loop over every site exceeds the
    # upstream connection idle timeout.
    semaphore = asyncio.Semaphore(10)
    deleted: set[tuple[str, int]] = set()
    kept: set[tuple[str, int]] = set()
    for purge_site, wanted in built.items():
        try:
            api = get_strategy_api(purge_site)
            live = {s.strategy_id for s in await api.list_strategies()}
        except (VEuPathDBError, OSError, RuntimeError) as exc:
            logger.warning(
                "WDK purge skipped for site",
                site=purge_site,
                strategies=len(wanted),
                error=str(exc),
            )
            kept.update((purge_site, strategy_id) for strategy_id in wanted)
            continue

        async def _delete_one(strategy_id: int, *, site: str = purge_site) -> bool:
            async with semaphore:
                try:
                    await get_strategy_api(site).delete_strategy(strategy_id)
                except (VEuPathDBError, OSError, RuntimeError) as exc:
                    logger.warning(
                        "Failed to delete WDK strategy during user data purge",
                        wdk_strategy_id=strategy_id,
                        site=site,
                        error=str(exc),
                    )
                    return False
                return True

        targets = sorted(wanted & live)
        outcomes = await asyncio.gather(
            *(_delete_one(strategy_id) for strategy_id in targets)
        )
        for strategy_id, done in zip(targets, outcomes, strict=True):
            (deleted if done else kept).add((purge_site, strategy_id))
    return WdkPurgeOutcome(frozenset(deleted), frozenset(kept))


async def _purge_related_data(
    session: AsyncSession,
    user_id: UUID,
    site_id: str | None,
    kept_runs: Sequence[str],
) -> tuple[int, int, int]:
    """Delete the calling application's gene sets, experiments and control sets.

    A run's persisted VEuPathDB strategy goes with its row: PathFinder created
    it, and nothing else names it. A run named in ``kept_runs`` still holds
    its strategy on the site, so its row stays and a later purge can finish.
    """
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
    if kept_runs:
        exp_del = exp_del.where(ExperimentRow.id.notin_(kept_runs))
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
