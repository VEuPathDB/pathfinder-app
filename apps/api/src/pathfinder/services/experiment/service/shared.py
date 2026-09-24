"""Shared helpers used by multiple experiment phases.

Small utility functions that don't belong to any single phase but are
called from several.
"""

from veupathdb_mcp.controls import ControlTestResult, run_positive_negative_controls

from pathfinder.services.experiment.helpers import (
    extract_and_hydrate_genes,
    intersection_config_from_config,
)
from pathfinder.services.experiment.metrics import metrics_from_control_result
from pathfinder.services.experiment.types import (
    Experiment,
    ExperimentConfig,
)


async def run_single_step_controls(config: ExperimentConfig) -> ControlTestResult:
    """Run single-step control tests with the config's parameters."""
    return await run_positive_negative_controls(
        intersection_config_from_config(config),
        positive_controls=config.positive_controls or None,
        negative_controls=config.negative_controls or None,
    )


async def apply_control_result(
    config: ExperimentConfig,
    experiment: Experiment,
    result: ControlTestResult,
) -> None:
    """Compute metrics and populate gene lists from a control-test result."""
    experiment.metrics = metrics_from_control_result(result)
    (
        experiment.true_positive_genes,
        experiment.false_negative_genes,
        experiment.false_positive_genes,
        experiment.true_negative_genes,
    ) = await extract_and_hydrate_genes(site_id=config.site_id, result=result)
