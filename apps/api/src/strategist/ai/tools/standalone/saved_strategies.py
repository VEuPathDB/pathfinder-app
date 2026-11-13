"""The FRAME lookup for strategies the user saved and can reuse."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone._frame_saved import saved_strategy_listing
from strategist.services.strategies.saved_library import SavedStrategyListing


class SavedStrategiesResult(CamelModel):
    """The strategies the user saved on this site, ordered by name."""

    saved_strategies: list[SavedStrategyListing] = Field(default_factory=list)


async def list_saved_strategies(
    ctx: RunContext[AgentDeps],
) -> ToolReturn[SavedStrategiesResult]:
    """List the strategies the user saved on this site and can reuse.

    Call this whenever the request starts from, or refers to, a strategy the
    user already has ("my saved strategy X", "the union I saved"). Each entry
    carries the name, the result count and the number of steps. Pass the name
    of the one the request means to ``set_criterion(saved_strategy=...)``, which
    reuses it as that criterion's input. When nothing in the listing matches the
    request, ask the user which one they mean; never build without it."""
    entries = await saved_strategy_listing(ctx)
    noun = "saved strategy" if len(entries) == 1 else "saved strategies"
    return with_summary(
        SavedStrategiesResult(saved_strategies=entries),
        f"{len(entries)} {noun} available",
        ctx=ctx,
    )
