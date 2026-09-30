"""The read-only tool that answers which genes a built step holds."""

from __future__ import annotations

from typing import Annotated, Protocol

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.tools.standalone.results import (
    named_or_root,
    spread_offsets,
    step_sample_seed,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.gene_sets.step_genes import (
    first_step_gene_ids,
    step_gene_ids_at,
)

STEP_IDS_CAP = 5000


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


async def read_step_ids(
    ctx: RunContext[StepIdsReader],
    wdk_step_id: int | None = None,
    limit: Annotated[int | None, Field(ge=1, le=STEP_IDS_CAP)] = None,
) -> ToolReturn[StepGeneIds]:
    """Return the gene ids a built step of this strategy holds. Read-only.

    This answers "which genes are in step X" and "is gene G in the result".
    It saves nothing; ``save_gene_set`` is a save the user asked for.

    Args:
        wdk_step_id: The WDK step id of a built step of this strategy. Leave
            it out for the root, which holds the result the researcher sees;
            name another step only when the researcher names that step.
        limit: How many ids to read, at most 5000. With a limit the ids are
            the genes ``get_sample_records`` reads at the same limit, spread
            over the step; leave it out for the first 5000 in the site's order.
            ``complete`` says whether the ids are every gene the step holds.
    """
    sync_state = ctx.deps.strategy_session.sync_state
    wdk_step_id = named_or_root(sync_state, wdk_step_id)
    live = sorted(set(sync_state.wdk_step_ids.values())) if sync_state else []
    if wdk_step_id not in live:
        raise ModelRetry(_no_such_step(wdk_step_id, live))
    site_id = ctx.deps.site_id
    if limit is None:
        read = await first_step_gene_ids(site_id, wdk_step_id, limit=STEP_IDS_CAP)
    else:
        seed = step_sample_seed(ctx.deps.strategy_session, wdk_step_id)
        read = await step_gene_ids_at(
            site_id,
            wdk_step_id,
            lambda total: spread_offsets(total, limit, seed=seed),
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
