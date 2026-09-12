"""The parameter-sweep half of the workbench facade: the grid and one trial."""

from veupathdb.domain.parameters import ParamValue

from pathfinder.services.parameter_optimization import sweep
from pathfinder.services.parameter_optimization.config import (
    OptimizationConfig,
    ParameterSpec,
    SweepControls,
    SweepTarget,
    SweepVariantResult,
    SweepVariantSpec,
)


def enumerate_variants(
    parameter_space: list[ParameterSpec],
    fixed_parameters: dict[str, ParamValue],
) -> list[SweepVariantSpec]:
    """The Cartesian product of the parameter grid, one variant per point."""
    return sweep.enumerate_variants(parameter_space, fixed_parameters)


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
