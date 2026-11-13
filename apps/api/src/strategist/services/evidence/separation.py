"""The separation part of the evidence facade: one run on the site, read as the
report Strategist shows and the offer it builds."""

from uuid import UUID

from veupathdb_mcp.separation import (
    SeparationProgress,
    SeparationRequest,
    ThreadSearch,
    TooFewControls,
    separate,
)

from strategist.domain.separation import SeparationReport
from strategist.domain.strategy.session import StrategyGraph
from strategist.platform.identity import SEPARATION_STRATEGY_NAME
from strategist.services.separation.offer import (
    separation_report,
    too_few_controls_report,
)
from strategist.services.separation.thread_searches import thread_searches
from strategist.services.strategies.search_sheets import radio_pairs_of
from strategist.services.strategies.sheet_params import sheet_params_for_searches


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
    if isinstance(result, TooFewControls):
        return too_few_controls_report(
            result, task_id=task_id, site_id=site_id, request=request
        )
    searches = {m.candidate.search_name for m in result.measured}
    sheets = await sheet_params_for_searches(site_id=site_id, search_names=searches)
    return separation_report(
        result,
        task_id=task_id,
        sheets=sheets,
        radio_pairs=await radio_pairs_of(site_id, searches),
    )
