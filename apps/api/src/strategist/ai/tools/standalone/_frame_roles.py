"""The role a criterion may take on a search."""

from __future__ import annotations

from pydantic_ai import RunContext
from veupathdb.wdk import WDKSearch

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone.catalog import record_transforms
from strategist.domain.refusal import Check, Problems, RefusalKey
from strategist.domain.strategy.operational_spec import CriterionRole
from strategist.services.strategies.record_classes import (
    plan_classes,
    transforms_accepting,
)


def saved_input_problems(
    criterion_id: str, role: CriterionRole, saved: str
) -> Problems:
    """A saved strategy or gene set is an input, so no criterion maps one."""
    if role != "transform":
        return Problems()
    return Problems.one(
        RefusalKey(check=Check.ROLE),
        f"{criterion_id} starts from a {saved}, which is an input and not "
        f'a search that maps one, so bind it with role="seed".',
    )


async def role_problems(
    ctx: RunContext[AgentDeps],
    definition: WDKSearch,
    role: CriterionRole,
) -> Problems:
    """A transform runs on a previous step, and every other role runs alone."""
    takes_an_input_step = bool(definition.allowed_primary_input_record_class_names)
    search_name = definition.url_segment
    key = RefusalKey(check=Check.ROLE)
    if role == "transform" and not takes_an_input_step:
        classes = plan_classes(ctx.deps.agent_state.operational_spec_draft)
        listings = await transforms_accepting(ctx.deps.site_id, classes)
        offered = sorted(listing.name for listing in listings)
        record_transforms(ctx, classes, listings)
        taking = ", ".join(sorted(classes)) if classes else "any record type"
        return Problems.one(
            key,
            f"{search_name} takes no input step, so it cannot be a transform. "
            f'Bind it with role="filter" or role="seed", or name one of the '
            f"transforms that take {taking}: {', '.join(offered)}.",
        )
    if role != "transform" and takes_an_input_step:
        return Problems.one(
            key,
            f"{search_name} runs on the results of a previous step, so it binds "
            f'with role="transform" and nothing else.',
        )
    return Problems()
