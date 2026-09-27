"""The Lead's tools that save, attach, list and read control sets and source their ids.

The Lead validates the researcher's ids against WDK and saves a control set.
"""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.turn_records import CreatedControlSet
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._id_arguments import parse_id_argument
from pathfinder.ai.tools.standalone.saved_control_sets import (
    ControlSetSummary,
    listed_control_sets,
)
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.services.evidence.control_sets import (
    UnknownControlSetError,
    control_ids_from_saved_gene_set,
    control_ids_from_strategy,
    create_control_set,
    get_control_set,
    new_control_set,
    saved_control_set,
    saved_control_sets,
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
    for scored runs. Pass the positive controls (genes that SHOULD be
    found) and optional negative controls (genes that should NOT). IDs that
    WDK doesn't recognize are dropped and reported back so you can tell the
    user about typos. Requires at least one recognized positive control. The
    saved set is attached to this conversation.
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
    ctx.deps.state.domain.attach_control_set(
        NamedControlSet(id=created.id, name=created.name)
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


async def list_control_sets(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[list[ControlSetSummary]]:
    """List every control set the user saved on this site, attached to this
    conversation or not, so you can find the one the researcher names."""
    runtime = ctx.deps.runtime
    sets = await saved_control_sets(
        runtime.db_session_factory, site_id=runtime.site_id, user_id=runtime.user_id
    )
    return listed_control_sets(ctx, sets)


async def use_control_set(
    ctx: RunContext[LeadDeps],
    control_set_id: str,
) -> ToolReturn[ControlSetSummary]:
    """Attach a saved control set the researcher names to this conversation.

    Call it when the researcher names a set saved earlier, by its name or as
    "my kinase controls"; ``list_control_sets`` gives its id. A control test,
    a sweep or a scored comparison runs only on a set attached to the
    conversation. ``build_control_set`` attaches the set it saves.
    """
    runtime = ctx.deps.runtime
    try:
        saved = await saved_control_set(
            runtime.db_session_factory,
            control_set_id,
            site_id=runtime.site_id,
            user_id=runtime.user_id,
        )
    except UnknownControlSetError as exc:
        msg = f"{exc.detail} list_control_sets names every saved set."
        raise ModelRetry(msg) from None
    ctx.deps.state.domain.attach_control_set(
        NamedControlSet(id=saved.control_set_id, name=saved.name)
    )
    summary = ControlSetSummary(
        control_set_id=saved.control_set_id,
        name=saved.name,
        positive_count=len(saved.positive_ids),
        negative_count=len(saved.negative_ids),
    )
    return with_summary(
        summary,
        f"{saved.name}: {summary.positive_count} positive, "
        f"{summary.negative_count} negative",
        ctx=ctx,
    )


class ControlSetIds(CamelModel):
    """The ids a saved control set holds."""

    control_set_id: str
    name: str
    positive_ids: list[str]
    negative_ids: list[str]


async def read_control_set(
    ctx: RunContext[LeadDeps],
    control_set_id: str,
) -> ToolReturn[ControlSetIds]:
    """Return the positive and negative ids of any saved control set, to name them.

    It reads a set attached to this conversation or not, and attaches nothing.
    A control test and a sweep run only on an attached set, by its
    ``control_set_id``. This saves nothing.
    """
    runtime = ctx.deps.runtime
    parsed = parse_id_argument(
        control_set_id, argument="control_set_id", names="control set"
    )
    async with runtime.db_session_factory() as session:
        held = await get_control_set(session, parsed, runtime.user_id)
    return with_summary(
        ControlSetIds(
            control_set_id=held.id,
            name=held.name,
            positive_ids=held.positive_ids,
            negative_ids=held.negative_ids,
        ),
        f"{held.name}: {len(held.positive_ids)} positive, "
        f"{len(held.negative_ids)} negative",
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
