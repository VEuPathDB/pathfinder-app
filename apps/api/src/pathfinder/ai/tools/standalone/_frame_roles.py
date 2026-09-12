"""The role a criterion may take on a search."""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext
from veupathdb.wdk import WDKSearch
from veupathdb_mcp import tool_payloads

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.operational_spec import CriterionRole


def refuse_a_transform_on_a_saved_strategy(
    criterion_id: str, role: CriterionRole
) -> None:
    """A saved strategy is an input, so no criterion maps one."""
    if role != "transform":
        return
    msg = (
        f"{criterion_id} starts from a saved strategy, which is an input and not "
        f'a search that maps one, so bind it with role="seed".'
    )
    raise ModelRetry(msg)


async def refuse_a_role_the_search_cannot_take(
    ctx: RunContext[AgentDeps],
    record_type: str,
    definition: WDKSearch,
    role: CriterionRole,
) -> None:
    """A transform runs on a previous step, and every other role runs alone."""
    takes_an_input_step = bool(definition.allowed_primary_input_record_class_names)
    search_name = definition.url_segment
    if role == "transform" and not takes_an_input_step:
        listings = await tool_payloads.list_transform_listings(
            ctx.deps.site_id, record_type
        )
        offered = sorted(listing.name for listing in listings)
        # A name the refusal offers is a name the model has seen.
        ctx.deps.agent_state.record_catalog_searches(offered)
        msg = (
            f"{search_name} takes no input step, so it cannot be a transform. "
            f'Bind it with role="filter" or role="seed", or name one of the '
            f"transforms on {record_type}: {', '.join(offered)}."
        )
        raise ModelRetry(msg)
    if role != "transform" and takes_an_input_step:
        msg = (
            f"{search_name} runs on the results of a previous step, so it binds "
            f'with role="transform" and nothing else.'
        )
        raise ModelRetry(msg)
