"""The read-only tool that answers which genes a built step holds."""

from __future__ import annotations

from typing import Annotated, Protocol

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.capabilities.site_reads import read_in_time
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.tools.standalone._result_models import MAX_SAMPLE_LIMIT
from pathfinder.ai.tools.standalone.results import (
    READ_DEADLINE_SECONDS,
    named_or_root,
    sample_page,
    step_sample_seed,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.gene_sets.step_genes import StepIds, first_step_gene_ids

STEP_IDS_CAP = 5000
# A whole listing reads up to five pages of a thousand ids each.
LISTING_DEADLINE_SECONDS = 60.0


class StepIdsReader(Protocol):
    """What a step read needs of its caller: the site, the thread's strategy and
    the turn's reads."""

    @property
    def site_id(self) -> str: ...

    @property
    def strategy_session(self) -> StrategySession: ...

    @property
    def turn_markers(self) -> TurnMarkers: ...


class StepGeneIds(CamelModel):
    """The first gene ids of a built step, and how many genes the step holds."""

    wdk_step_id: int
    gene_ids: list[str]
    total: int
    complete: bool


def _no_such_step(wdk_step_id: int, live: list[int]) -> str:
    held = ", ".join(str(step) for step in live) or "none"
    return (
        f"wdk_step_id {wdk_step_id} names no built step of this conversation's "
        f"strategy. The built steps: {held}."
    )


async def _sampled_ids(deps: StepIdsReader, wdk_step_id: int, limit: int) -> StepIds:
    """The ids ``get_sample_records`` reads at the same limit, in its order."""
    session = deps.strategy_session
    graph = session.get_graph(None)
    sampled = await sample_page(
        deps.site_id,
        wdk_step_id,
        limit=limit,
        attributes=["primary_key"],
        record_type=(graph.record_type if graph is not None else None) or "transcript",
        seed=step_sample_seed(session, wdk_step_id),
    )
    return StepIds(gene_ids=sampled.gene_ids, total=sampled.result.total_count)


async def read_step_ids(
    ctx: RunContext[StepIdsReader],
    wdk_step_id: int | None = None,
    limit: Annotated[int | None, Field(ge=1, le=MAX_SAMPLE_LIMIT)] = None,
) -> ToolReturn[StepGeneIds]:
    """Return the gene ids a built step of this strategy holds. Read-only.

    This answers "which genes are in step X" and "is gene G in the result".
    It saves nothing; ``save_gene_set`` is a save the user asked for.

    Args:
        wdk_step_id: The WDK step id of a built step of this strategy. Leave
            it out for the root, which holds the result the researcher sees;
            name another step only when the researcher names that step.
        limit: How many ids to read, at most 100. With a limit the ids are
            the genes ``get_sample_records`` reads at the same limit, spread
            over the step; leave it out for the first 5000 in the site's order.
            ``complete`` says whether the ids are every gene the step holds.
    """
    sync_state = ctx.deps.strategy_session.sync_state
    wdk_step_id = named_or_root(sync_state, wdk_step_id)
    live = sorted(set(sync_state.wdk_step_ids.values())) if sync_state else []
    if wdk_step_id not in live:
        raise ModelRetry(_no_such_step(wdk_step_id, live))
    subject = f"step {wdk_step_id}"
    if limit is None:
        read = await read_in_time(
            "read_step_ids",
            subject,
            first_step_gene_ids(ctx.deps.site_id, wdk_step_id, limit=STEP_IDS_CAP),
            deadline=LISTING_DEADLINE_SECONDS,
        )
    else:
        read = await read_in_time(
            "read_step_ids",
            subject,
            _sampled_ids(ctx.deps, wdk_step_id, limit),
            deadline=READ_DEADLINE_SECONDS,
        )
    complete = len(read.gene_ids) >= read.total
    ctx.deps.turn_markers.record_listed_genes(wdk_step_id, read.gene_ids)
    return with_summary(
        StepGeneIds(
            wdk_step_id=wdk_step_id,
            gene_ids=read.gene_ids,
            total=read.total,
            complete=complete,
        ),
        f"{len(read.gene_ids):,} of {count_noun(read.total, 'gene')}",
        ctx=ctx,
        status="ok" if read.gene_ids else "empty",
    )
