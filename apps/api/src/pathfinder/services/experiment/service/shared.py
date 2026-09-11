"""Shared helpers used by multiple experiment phases.

Small utility functions that don't belong to any single phase but are
called from several.
"""

from veupathdb.domain.parameters.values import ParamValue
from veupathdb_mcp.controls import ControlTestResult, run_positive_negative_controls

from pathfinder.services.experiment.helpers import (
    extract_and_hydrate_genes,
    intersection_config_from_config,
)
from pathfinder.services.experiment.metrics import metrics_from_control_result
from pathfinder.services.experiment.types import (
    Experiment,
    ExperimentConfig,
    ExperimentMetrics,
)


async def run_single_step_controls(
    config: ExperimentConfig,
    parameters: dict[str, ParamValue],
) -> ControlTestResult:
    """Run single-step control tests with the given parameters."""
    return await run_positive_negative_controls(
        intersection_config_from_config(config, target_parameters=parameters),
        positive_controls=config.positive_controls or None,
        negative_controls=config.negative_controls or None,
    )


async def apply_control_result(
    config: ExperimentConfig,
    experiment: Experiment,
    result: ControlTestResult,
) -> ExperimentMetrics:
    """Compute metrics and populate gene lists from a control-test result."""
    metrics = metrics_from_control_result(result)
    experiment.metrics = metrics
    (
        experiment.true_positive_genes,
        experiment.false_negative_genes,
        experiment.false_positive_genes,
        experiment.true_negative_genes,
    ) = await extract_and_hydrate_genes(
        site_id=config.site_id,
        result=result,
        negative_controls=config.negative_controls,
    )
    return metrics
