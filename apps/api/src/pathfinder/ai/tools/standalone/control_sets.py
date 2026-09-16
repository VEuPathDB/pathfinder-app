"""Lead tools for sourcing + persisting control gene sets (Phase 2b).

A scored experiment needs positive/negative control gene lists. These tools
let the Lead validate user-provided IDs against WDK and persist a ControlSet,
plus list and pull from existing control sets / saved gene sets / strategies.
"""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.state import CreatedControlSet
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._id_arguments import parse_id_argument
from pathfinder.services.workbench.control_sets import (
    control_ids_from_saved_gene_set,
    control_ids_from_strategy,
    create_control_set,
    list_control_sets_for_site,
    new_control_set,
    validate_control_ids,
)


class BuiltControlSet(CamelModel):
    control_set_id: str
    name: str
    positive_count: int
    negative_count: int
    unresolved_positive: list[str]
    unresolved_negative: list[str]


async def build_control_set(
    ctx: RunContext[LeadDeps],
    name: str,
    positive_ids: list[str],
    negative_ids: list[str] | None = None,
    record_type: str = "transcript",
) -> ToolReturn[BuiltControlSet]:
    """Validate gene IDs against WDK and save them as a reusable control set
    for scored experiments. Pass the positive controls (genes that SHOULD be
    found) and optional negative controls (genes that should NOT). IDs that
    WDK doesn't recognize are dropped and reported back so you can tell the
    user about typos. Requires at least one recognized positive control.
    """
    runtime = ctx.deps.runtime

    pos = await validate_control_ids(
        runtime.site_id, positive_ids, record_type=record_type
    )
    neg = await validate_control_ids(
        runtime.site_id, negative_ids or [], record_type=record_type
    )
    if not pos.valid_ids:
        msg = (
            "No positive control IDs were recognized by WDK "
            f"(unresolved: {pos.unresolved_ids}). Check the IDs and retry."
        )
        raise ModelRetry(msg)

    async with runtime.db_session_factory() as session:
        created = await create_control_set(
            session,
            new_control_set(
                name=name,
                site_id=runtime.site_id,
                record_type=record_type,
                positive_ids=pos.valid_ids,
                negative_ids=neg.valid_ids,
                source="chat",
            ),
            user_id=runtime.user_id,
        )
        await session.commit()

    ctx.deps.state.turn_markers.record_control_set(
        CreatedControlSet(id=created.id, name=created.name),
    )
    return with_summary(
        BuiltControlSet(
            control_set_id=created.id,
            name=created.name,
            positive_count=len(pos.valid_ids),
            negative_count=len(neg.valid_ids),
            unresolved_positive=pos.unresolved_ids,
            unresolved_negative=neg.unresolved_ids,
        ),
        f"{created.name}: {len(pos.valid_ids)} positive, {len(neg.valid_ids)} negative",
        ctx=ctx,
    )


class ControlSetSummary(CamelModel):
    control_set_id: str
    name: str
    positive_count: int
    negative_count: int


async def list_control_sets(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[list[ControlSetSummary]]:
    """List the user's saved control sets for this site, so you can offer them
    as the scoring basis instead of asking for new IDs."""
    runtime = ctx.deps.runtime
    async with runtime.db_session_factory() as session:
        sets = await list_control_sets_for_site(
            session, site_id=runtime.site_id, user_id=runtime.user_id
        )
    return with_summary(
        [
            ControlSetSummary(
                control_set_id=cs.id,
                name=cs.name,
                positive_count=len(cs.positive_ids),
                negative_count=len(cs.negative_ids),
            )
            for cs in sets
        ],
        f"{len(sets)} control sets",
        ctx=ctx,
    )


async def read_gene_ids_from_gene_set(
    ctx: RunContext[LeadDeps],
    gene_set_id: str,
) -> ToolReturn[list[str]]:
    """Return the gene IDs of a saved workbench gene set, to use as controls.

    This saves nothing. Call build_control_set to save a control set.
    """
    ids = await control_ids_from_saved_gene_set(ctx.deps.runtime.user_id, gene_set_id)
    return with_summary(
        ids,
        f"{len(ids)} ids from gene set {gene_set_id}",
        ctx=ctx,
        status="ok" if ids else "empty",
    )


async def read_gene_ids_from_strategy(
    ctx: RunContext[LeadDeps],
    strategy_id: str,
) -> ToolReturn[list[str]]:
    """Return the result gene IDs of another strategy (a conversation id), to
    use as positive or negative controls.

    This saves nothing. Call build_control_set to save a control set.
    """
    runtime = ctx.deps.runtime
    parsed = parse_id_argument(
        strategy_id, argument="strategy_id", names="conversation"
    )
    async with runtime.db_session_factory() as session:
        result = await control_ids_from_strategy(
            session,
            parsed,
            runtime.site_id,
            runtime.user_id,
        )
    if result.error:
        msg = f"Could not import from strategy {strategy_id}: {result.error}"
        raise ModelRetry(msg)
    return with_summary(
        result.gene_ids,
        f"{len(result.gene_ids)} ids from strategy {strategy_id}",
        ctx=ctx,
        status="ok" if result.gene_ids else "empty",
    )
