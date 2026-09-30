"""The job that keeps the auto-imported gene set on the strategy's current root.

A write defers the job and answers when WDK holds the edit. The job reads the
stored root when it runs, so a late job never writes an older answer.
"""

from time import monotonic
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from assistant_core.tasks.app import task_app
from assistant_core.tasks.job_context import durable_job_context
from assistant_core.tasks.names import DEFAULT_QUEUE
from procrastinate.exceptions import AlreadyEnqueued
from pydantic import BaseModel, ConfigDict, JsonValue
from veupathdb.errors import VEuPathDBError

from pathfinder.domain.strategy.revision import answer_revision, parse_strategy_ast
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.write_lock import (
    strategy_write_lock,
    writes_a_thread,
)

logger = get_logger(__name__)

GENE_SET_REFRESH_TASK = "strategy:refresh_gene_set"


class GeneSetRefreshJob(BaseModel):
    """The kwargs of one refresh job: the thread, its site, the carried token."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    site_id: str
    job_context: dict[str, JsonValue]


async def defer_the_gene_set_refresh(deps: StrategyMutationContext) -> None:
    """Queue the thread's refresh, once while one waits.

    Refreshes of one thread run one at a time, apart from the thread's turns.
    A job that waits already reads the root this write leaves.
    """
    if deps.conversation_id is None or not writes_a_thread(deps):
        return
    refresh_lock = f"gene-set-refresh:{deps.conversation_id}"
    job = GeneSetRefreshJob(
        conversation_id=deps.conversation_id,
        site_id=deps.site_id,
        job_context=durable_job_context().capture().model_dump(mode="json"),
    )
    deferrer = task_app().configure_task(
        name=GENE_SET_REFRESH_TASK,
        queue=DEFAULT_QUEUE,
        lock=refresh_lock,
        queueing_lock=refresh_lock,
    )
    try:
        await deferrer.defer_async(payload=job.model_dump(mode="json"))
    except AlreadyEnqueued:
        return


async def refresh_the_strategy_gene_set(
    *, conversation_id: UUID, site_id: str
) -> GeneSet | None:
    """The set auto-import made takes the answer of the stored root.

    A set the thread links but did not import is the user's, so it is left as
    it stands. A set that already holds this root's answer is not read again.
    Returns the set as it stands after the job, or None when there is none.
    """
    async with strategy_write_lock(conversation_id, async_session_factory) as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    if (
        not strategy.gene_set_auto_imported
        or strategy.gene_set_id is None
        or strategy.wdk_strategy_id is None
    ):
        return None
    revision = answer_revision(parse_strategy_ast(strategy.strategy_ast))
    held = await get_gene_set_store().get(strategy.gene_set_id)
    if held is None or held.answer_revision == revision:
        return held
    started = monotonic()
    service = GeneSetService(get_gene_set_store())
    try:
        refreshed = await service.resync_strategy(
            strategy.gene_set_id,
            wdk_strategy_id=strategy.wdk_strategy_id,
            site_id=site_id,
            answer_revision=revision,
        )
    except (VEuPathDBError, RuntimeError) as exc:
        logger.warning(
            "Failed to refresh the strategy's gene set",
            conversation_id=str(conversation_id),
            error=str(exc),
            seconds=round(monotonic() - started, 2),
        )
        return held
    if refreshed is not None:
        logger.info(
            "Refreshed the strategy's gene set",
            conversation_id=str(conversation_id),
            gene_set_id=refreshed.id,
            gene_count=len(refreshed.gene_ids),
            seconds=round(monotonic() - started, 2),
        )
    return refreshed
