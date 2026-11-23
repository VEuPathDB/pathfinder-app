"""The parameter-sweep part of the evidence facade: the grid and one trial."""

from collections.abc import Mapping

from veupathdb import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.catalog import organism_parameter_of

from strategist.domain.unread import Unread
from strategist.services.parameter_optimization import sweep, tunable
from strategist.services.parameter_optimization.config import (
    OptimizationConfig,
    SweepControls,
    SweepPlan,
    SweepTarget,
    SweepVariantResult,
    SweepVariantSpec,
)
from strategist.services.site_errors import site_words

logger = get_logger(__name__)


def enumerate_variants(plan: SweepPlan) -> list[SweepVariantSpec]:
    """The Cartesian product of the parameter grid, one variant per point."""
    return sweep.enumerate_variants(plan)


async def run_trial(
    variant: SweepVariantSpec,
    *,
    target: SweepTarget,
    controls: SweepControls,
    score_cfg: OptimizationConfig,
    progress_callback: sweep.ProgressFn | None = None,
) -> SweepVariantResult:
    """Evaluate one variant against the controls and score the result."""
    return await sweep.run_trial(
        variant,
        target=target,
        controls=controls,
        score_cfg=score_cfg,
        progress_callback=progress_callback,
    )


async def sweep_plan_for_step(
    site_id: str,
    record_type: str,
    search_name: str,
    step_values: Mapping[str, str],
    *,
    names: list[str] | None = None,
    budget: int,
) -> SweepPlan:
    """The grid a sweep of this step runs, capped at ``budget`` trials."""
    declarations = await tunable.search_declarations(site_id, record_type, search_name)
    return tunable.sweep_plan(
        search_name,
        declarations,
        step_values,
        names=names,
        budget=budget,
        organism=await organism_parameter_of(site_id, declarations),
    )


async def tunable_parameters_of_search(
    site_id: str,
    record_type: str,
    search_name: str,
) -> list[str] | Unread:
    """The parameters of this search a sweep can vary, or why they were not read."""
    try:
        published = await tunable.search_parameter_metadata(
            site_id, record_type, search_name
        )
    except (VEuPathDBError, OSError) as exc:
        logger.warning(
            "The tunable parameters of a search could not be read",
            search_name=search_name,
            error=str(exc),
        )
        return Unread(reason=site_words(exc))
    return tunable.tunable_parameter_names(published)
