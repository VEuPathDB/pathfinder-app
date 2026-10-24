from __future__ import annotations

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext
from veupathdb_mcp.catalog import ortho_taxonomy

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.compare_readings import reading_departures
from pathfinder.domain.strategy.computed_groups import bound_comparisons
from pathfinder.domain.strategy.expression_handles import bound_patterns


async def hold_a_comparison_to_its_reading(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    match output:
        case FrameResult():
            asked = output.comparison_reading
        case _:
            return output
    if asked is None:
        return output
    state = ctx.deps.agent_state
    spec = state.operational_spec_draft
    bound = [
        *bound_patterns(state.built_expressions, spec),
        *bound_comparisons(state.computed_comparisons, spec),
    ]
    tree = await ortho_taxonomy(ctx.deps.site_id) if bound else None
    if tree is None:
        return output
    departures = reading_departures(asked, bound, tree)
    if not departures:
        return output
    if not may_refuse(ctx, state.refusals):
        return output.with_gap(
            "comparison_reading_departs",
            f"The request compares two genome sets by {asked}, and the bound "
            "comparison reads another way.",
        )
    state.refusals += 1
    raise ModelRetry(" ".join(departures))


__all__ = ["hold_a_comparison_to_its_reading"]
