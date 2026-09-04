"""Batch parameter sweeps with concurrency control, timeouts, and SSE events."""

import asyncio
from collections.abc import AsyncIterator
from typing import Literal

from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel, RoundedFloat

from pathfinder.domain.parameters.value_codec import from_wire
from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.domain.strategy.tree import walk
from pathfinder.integrations.veupathdb.factory import get_strategy_api
from pathfinder.platform.errors import AppError, ValidationError
from pathfinder.services.control_helpers import (
    cleanup_internal_control_test_strategies,
)
from pathfinder.services.control_tests import (
    IntersectionConfig,
    run_positive_negative_controls,
)
from pathfinder.services.experiment.helpers import ControlsContext
from pathfinder.services.experiment.metrics import metrics_from_control_result
from pathfinder.services.experiment.tree_evaluation import (
    run_controls_against_tree,
)
from pathfinder.services.experiment.types import (
    ControlTestResult,
    Experiment,
    ExperimentMetrics,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Typed SSE events
# ---------------------------------------------------------------------------


class SweepMetrics(CamelModel):
    """Subset of :class:`ExperimentMetrics` emitted per sweep point."""

    sensitivity: RoundedFloat
    specificity: RoundedFloat
    precision: RoundedFloat
    f1_score: RoundedFloat
    mcc: RoundedFloat
    balanced_accuracy: RoundedFloat
    total_results: int
    false_positive_rate: RoundedFloat


class SweepPoint(CamelModel):
    """A completed sweep point: the value with either metrics or an error."""

    value: float | str
    metrics: SweepMetrics | None = None
    error: str | None = None


class SweepPointEvent(CamelModel):
    """Emitted each time a sweep point finishes."""

    type: Literal["sweep_point"] = "sweep_point"
    point: SweepPoint
    completed_count: int
    total_count: int


class SweepCompleteEvent(CamelModel):
    """Terminal event that carries every sweep point in sorted order."""

    type: Literal["sweep_complete"] = "sweep_complete"
    parameter: str
    sweep_type: Literal["numeric", "categorical"]
    points: list[SweepPoint]


SweepEvent = SweepPointEvent | SweepCompleteEvent
"""Union of all threshold-sweep event types."""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SWEEP_CONCURRENCY = 3
"""Maximum parallel WDK control-test runs per sweep."""

SWEEP_TIMEOUT_S = 4 * 60
"""Server-side timeout for the entire sweep."""

SWEEP_POINT_TIMEOUT_S = 90
"""Timeout for one sweep point."""

# ---------------------------------------------------------------------------
# Sweep validation helpers
# ---------------------------------------------------------------------------


def compute_sweep_values(
    *,
    sweep_type: str,
    values: list[str] | None,
    lo: float | None,
    hi: float | None,
    steps: int,
) -> list[str]:
    """Compute the list of parameter values for a sweep."""
    if sweep_type == "categorical":
        if not values or len(values) == 0:
            raise ValidationError(
                title="Missing values",
                detail="Categorical sweep requires a non-empty 'values' list.",
            )
        return values

    if lo is None or hi is None:
        raise ValidationError(
            title="Missing range",
            detail="Numeric sweep requires 'min' and 'max'.",
        )
    denom = steps - 1 if steps > 1 else 1
    step_size = (hi - lo) / denom
    return [str(lo + i * step_size) for i in range(steps)]


def validate_sweep_parameter(exp: Experiment, param_name: str) -> None:
    """Raise a ValidationError when the experiment config has no such parameter."""
    if exp.config.is_tree_mode and exp.config.step_tree is not None:
        if _tree_has_parameter(exp.config.step_tree, param_name):
            return
    elif param_name in exp.config.parameters:
        return

    raise ValidationError(
        title="Parameter not found",
        detail=f"Parameter '{param_name}' is not in this experiment's config.",
    )


def _tree_has_parameter(tree: StrategyStepNode, param_name: str) -> bool:
    """Report whether any node of a plan step tree holds the parameter."""
    return any(param_name in node.parameters for node in walk(tree))


def _metrics_to_sweep(m: ExperimentMetrics) -> SweepMetrics:
    """Project experiment metrics onto the sweep metrics subset."""
    return SweepMetrics(
        sensitivity=m.sensitivity,
        specificity=m.specificity,
        precision=m.precision,
        f1_score=m.f1_score,
        mcc=m.mcc,
        balanced_accuracy=m.balanced_accuracy,
        total_results=m.total_results,
        false_positive_rate=m.false_positive_rate,
    )


# ---------------------------------------------------------------------------
# Sweep point execution
# ---------------------------------------------------------------------------


async def run_sweep_point(
    *,
    exp: Experiment,
    param_name: str,
    value: str,
    is_categorical: bool,
) -> SweepPoint:
    """Set the parameter to one value and evaluate it against the controls."""
    try:
        response_value: float | str = float(value) if not is_categorical else value
    except ValueError:
        response_value = value

    try:
        if exp.config.is_tree_mode:
            result = await _run_sweep_point_tree(
                exp=exp,
                param_name=param_name,
                value=value,
            )
        else:
            modified_params = dict(exp.config.parameters)
            existing = modified_params.get(param_name)
            kind = existing.type if existing is not None else "string"
            modified_params[param_name] = from_wire(kind, value)
            result = await asyncio.wait_for(
                run_positive_negative_controls(
                    IntersectionConfig.from_experiment_config(
                        exp.config, target_parameters=modified_params
                    ),
                    positive_controls=exp.config.positive_controls or None,
                    negative_controls=exp.config.negative_controls or None,
                    skip_cleanup=True,
                ),
                timeout=SWEEP_POINT_TIMEOUT_S,
            )
        m = metrics_from_control_result(result)
        return SweepPoint(value=response_value, metrics=_metrics_to_sweep(m))
    except (
        AppError,
        OSError,
        RuntimeError,
        TimeoutError,
    ) as exc:
        logger.warning(
            "Threshold sweep point failed",
            param=param_name,
            value=value,
            error=str(exc),
        )
        return SweepPoint(value=response_value, error=str(exc))


async def _run_sweep_point_tree(
    *,
    exp: Experiment,
    param_name: str,
    value: str,
) -> ControlTestResult:
    """Run one sweep point over a copy of the step tree."""
    if exp.config.step_tree is None:
        msg = "step_tree must be set in tree mode"
        raise ValidationError(detail=msg)

    tree = exp.config.step_tree.model_copy(deep=True)

    for node in walk(tree):
        existing = node.parameters.get(param_name)
        if existing is not None:
            node.parameters[param_name] = from_wire(existing.type, value)

    return await asyncio.wait_for(
        run_controls_against_tree(
            ControlsContext.from_config(exp.config),
            tree,
        ),
        timeout=SWEEP_POINT_TIMEOUT_S,
    )


# ---------------------------------------------------------------------------
# Sweep orchestration
# ---------------------------------------------------------------------------


async def cleanup_before_sweep(site_id: str) -> None:
    """Best-effort cleanup of leaked internal control-test strategies."""
    try:
        api = get_strategy_api(site_id)
        strategies = await api.list_strategies()
        await cleanup_internal_control_test_strategies(api, strategies)
    except (AppError, OSError, RuntimeError) as exc:
        logger.warning(
            "Pre-sweep cleanup of leaked control-test strategies failed",
            site_id=site_id,
            error=str(exc),
        )


async def generate_sweep_events(
    *,
    exp: Experiment,
    param_name: str,
    sweep_type: Literal["numeric", "categorical"],
    sweep_values: list[str],
) -> AsyncIterator[SweepEvent]:
    """Run the full sweep and yield a point event per result, then a final event."""
    is_categorical = sweep_type == "categorical"
    total_points = len(sweep_values)

    await cleanup_before_sweep(exp.config.site_id)

    semaphore = asyncio.Semaphore(SWEEP_CONCURRENCY)
    completed_count = 0
    all_points: list[SweepPoint] = []

    async def _bounded_point(val: str) -> SweepPoint:
        async with semaphore:
            return await run_sweep_point(
                exp=exp,
                param_name=param_name,
                value=val,
                is_categorical=is_categorical,
            )

    tasks = {asyncio.ensure_future(_bounded_point(v)): v for v in sweep_values}

    try:
        async with asyncio.timeout(SWEEP_TIMEOUT_S):
            for coro in asyncio.as_completed(tasks):
                point = await coro
                completed_count += 1
                all_points.append(point)
                yield SweepPointEvent(
                    point=point,
                    completed_count=completed_count,
                    total_count=total_points,
                )

    except TimeoutError:
        logger.warning(
            "Threshold sweep timed out",
            param=param_name,
            completed=completed_count,
            total=total_points,
        )
        for task in tasks:
            task.cancel()

    # Categorical points keep the input order. Numeric points sort by value.
    if is_categorical:
        order = {v: i for i, v in enumerate(sweep_values)}
        all_points.sort(key=lambda p: order.get(str(p.value), 0))
    else:

        def _numeric_value(p: SweepPoint) -> float:
            try:
                return float(str(p.value))
            except ValueError, TypeError:
                return 0.0

        all_points.sort(key=_numeric_value)

    yield SweepCompleteEvent(
        parameter=param_name,
        sweep_type=sweep_type,
        points=all_points,
    )
