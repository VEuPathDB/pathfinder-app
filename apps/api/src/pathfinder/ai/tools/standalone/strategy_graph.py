"""Standalone strategy graph inspection tools for pydantic-ai migration.

Each function takes ``RunContext[AgentDeps]`` and mirrors the original
:class:`StrategyGraphOps` methods exactly.
"""

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, JsonValue
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp import ToolErrorPayload, tool_error

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.graph_helpers import (
    count_summary,
    serialize_step,
)
from pathfinder.domain.strategy.build_outcome import built_counts
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.eda.analysis_kinds import (
    read_the_unread_kinds,
    unread_analyses,
)
from pathfinder.services.eda.export import (
    exported_analysis,
)
from pathfinder.services.strategies.schemas import StepResponse

logger = get_logger(__name__)


def _root_count(
    graph: StrategyGraph, sync_state: SyncStateProtocol | None
) -> int | None:
    """The strategy root's WDK count, or nothing when it carries none."""
    return built_counts(graph, sync_state).root_count


class StrategySummaryResponse(CamelModel):
    """Summary metadata for a strategy graph."""

    graph_id: str
    graph_name: str | None = None
    record_type: str | None = None
    wdk_strategy_id: JsonValue = None
    is_built: bool = False
    step_count: int = 0
    description: str | None = None
    steps: list[StepResponse] | None = None
    revision: str = ""
    """Fingerprint of the strategy's inputs; pass to ``apply_operations``.

    Hashes search names, parameters, operators and tree shape only, so a
    refreshed count never looks like an edit. Empty for no strategy.
    """
    # What each study step selects, by step id, read from its analysis document.
    analyses: dict[str, str] = Field(default_factory=dict)
    # The study steps whose analysis the site did not describe: pending checks.
    unread_analyses: list[str] = Field(default_factory=list)


async def get_strategy(
    ctx: RunContext[AgentDeps],
    *,
    summary_only: bool = True,
) -> ToolReturn[StrategySummaryResponse | ToolErrorPayload]:
    """Get this conversation's strategy -- summary metadata or full step details.

    By default returns a lightweight summary (step count, record type, build status).
    Pass summary_only=false for per-step details including WDK step IDs and estimated
    result counts.
    """
    deps = ctx.deps
    session = deps.strategy_session
    graph = session.graph
    if graph is None:
        return with_summary(
            tool_error(ErrorCode.NOT_FOUND, "This conversation holds no strategy yet."),
            "No strategy yet",
            ctx=ctx,
            status="empty",
        )

    sync_state = session.sync_state
    wdk_strategy_id = sync_state.wdk_strategy_id if sync_state else None
    await read_the_unread_kinds(site_id=deps.site_id, graph=graph)

    steps: list[StepResponse] | None = None
    if not summary_only:
        steps = [
            serialize_step(graph, step, sync_state) for step in graph.steps.values()
        ]

    summary = StrategySummaryResponse(
        graph_id=graph.id,
        graph_name=graph.name,
        record_type=graph.record_type,
        wdk_strategy_id=wdk_strategy_id,
        is_built=wdk_strategy_id is not None,
        step_count=len(graph.steps),
        description=graph.description,
        steps=steps,
        revision=strategy_revision(graph.to_strategy_ast(sync_state=sync_state)),
        analyses={
            step_id: binding.words
            for step_id, step in graph.steps.items()
            if (
                binding := exported_analysis(
                    graph.analysis_kind_of(step_id), step.parameters
                )
            )
            is not None
        },
        unread_analyses=unread_analyses(graph),
    )
    if not graph.steps:
        return with_summary(summary, "No strategy yet", ctx=ctx, status="empty")
    line, status = count_summary(
        len(graph.steps), _root_count(graph, sync_state), graph.record_type
    )
    return with_summary(summary, line, ctx=ctx, status=status)
