"""Worker-side body of the strategy gene-set refresh job."""

from __future__ import annotations

from assistant_core.tasks.job_context import durable_job_context
from assistant_core.tasks.scope import attach_conversation_application
from pydantic import JsonValue

from pathfinder.services.strategies.gene_set_refresh import (
    GeneSetRefreshJob,
    refresh_the_strategy_gene_set,
)


async def refresh_strategy_gene_set(payload: dict[str, JsonValue]) -> None:
    """Refresh the thread's set as the researcher whose write deferred the job."""
    job = GeneSetRefreshJob.model_validate(payload)
    carried = durable_job_context()
    async with (
        carried.restore(carried.state_type.model_validate(job.job_context)),
        attach_conversation_application(job.conversation_id),
    ):
        await refresh_the_strategy_gene_set(
            conversation_id=job.conversation_id, site_id=job.site_id
        )
