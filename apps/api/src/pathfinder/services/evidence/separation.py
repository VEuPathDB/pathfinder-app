"""The separation part of the evidence facade: one run on the site, read as the
report PathFinder shows and the offer it builds."""

from uuid import UUID

from veupathdb_mcp.separation import (
    SeparationProgress,
    SeparationRequest,
    ThreadSearch,
    separate,
)

from pathfinder.domain.separation import SeparationReport
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.platform.identity import SEPARATION_STRATEGY_NAME
from pathfinder.services.separation.offer import separation_report
from pathfinder.services.separation.thread_searches import thread_searches


def searches_the_thread_runs(graph: StrategyGraph | None) -> list[ThreadSearch]:
    """The leaves of the thread's strategy, as a run's own candidates."""
    return thread_searches(graph)


async def separate_controls(
    site_id: str,
    request: SeparationRequest,
    *,
    task_id: UUID,
    progress: SeparationProgress,
) -> SeparationReport:
    """Measure the candidates on the site and report the strategy they assemble.

    The run's internal strategies carry this deployment's name, so its cleanup
    deletes what an interrupted run left.
    """
    result = await separate(
        site_id,
        request,
        strategy_name=SEPARATION_STRATEGY_NAME,
        progress=progress,
    )
    return separation_report(result, task_id=task_id)
