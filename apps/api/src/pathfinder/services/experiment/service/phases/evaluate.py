"""Evaluation phase: the control test of the experiment's search, and its metrics."""

from pathfinder.services.experiment.service.context import PhaseContext
from pathfinder.services.experiment.service.shared import (
    apply_control_result,
    run_single_step_controls,
)


async def phase_evaluate(pctx: PhaseContext) -> None:
    """Run the control test, compute metrics, and fill the gene lists."""
    config, experiment = pctx.config, pctx.experiment
    result = await run_single_step_controls(config)
    await apply_control_result(config, experiment, result)
    pctx.store.save(experiment)
