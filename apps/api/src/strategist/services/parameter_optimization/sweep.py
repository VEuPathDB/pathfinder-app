from __future__ import annotations

from collections.abc import Awaitable, Callable
from itertools import product

from pydantic import JsonValue
from veupathdb.domain.parameters import (
    FilterProposals,
    ParamValue,
    to_decoded_map,
    to_wire,
)
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.controls import (
    ControlTestResult,
    IntersectionConfig,
    run_positive_negative_controls,
)

from strategist.platform.identity import CONTROL_TEST_STRATEGY_NAME
from strategist.services.parameter_optimization.builders import (
    _extract_trial_metrics,
)
from strategist.services.parameter_optimization.config import (
    OptimizationConfig,
    ParameterSpec,
    SweepControls,
    SweepPlan,
    SweepTarget,
    SweepVariantResult,
    SweepVariantSpec,
)
from strategist.services.parameter_optimization.scoring import _compute_score

# Default number of equally-spaced levels to materialise for a continuous
# (numeric) parameter when the user did not provide a ``step``. Five gives
# a useful coarse grid without exploding the Cartesian product.
_DEFAULT_NUMERIC_LEVELS = 5

ProgressFn = Callable[[float, str, dict[str, JsonValue] | None], Awaitable[None]]


def _level(declared: WDKParameter, level: JsonValue) -> ParamValue:
    stated = [level] if declared.type == "multi-pick-vocabulary" else level
    match declared.read_stated(stated):
        case FilterProposals():
            msg = f"{declared.name} is a filter, and a sweep varies no filter"
            raise ValueError(msg)
        case read:
            return read


def _number(value: ParamValue) -> float | None:
    try:
        return float(to_wire(value))
    except ValueError:
        return None


def _with_held(levels: list[ParamValue], held: ParamValue | None) -> list[ParamValue]:
    number = None if held is None else _number(held)
    if held is None or number is None:
        return levels
    return [held if _number(level) == number else level for level in levels]


def enumerate_spec_values(spec: ParameterSpec) -> list[JsonValue]:
    """Each level of a ParameterSpec in its stated form."""
    if spec.param_type == "categorical":
        return [str(c) for c in spec.choices or []]

    if spec.param_type == "integer":
        lo = int(spec.min if spec.min is not None else 0)
        hi = int(spec.max if spec.max is not None else 10)
        step = int(spec.step) if spec.step else max(1, (hi - lo) // 10)
        return [float(v) for v in range(lo, hi + 1, step)]

    # numeric
    lo_f = spec.min if spec.min is not None else 0.0
    hi_f = spec.max if spec.max is not None else 1.0
    if spec.step:
        values: list[JsonValue] = []
        v = lo_f
        while v <= hi_f:
            values.append(v)
            v += spec.step
        return values or [lo_f]
    n = _DEFAULT_NUMERIC_LEVELS
    if n <= 1:
        return [lo_f]
    step_size = (hi_f - lo_f) / (n - 1)
    return [lo_f + i * step_size for i in range(n)]


def enumerate_variants(plan: SweepPlan) -> list[SweepVariantSpec]:
    """Build the Cartesian product of the parameter grid.

    Each level is read by its parameter's declaration, and a level equal to the
    held number is the held value. Each combination becomes one
    :class:`SweepVariantSpec` whose ``params`` dict merges the fixed
    parameters under the swept values. Variants are id'd ``v0..vN-1``
    in iteration order so the UI lane order is stable.
    """
    if not plan.parameter_space:
        msg = "parameter_space must contain at least one ParameterSpec"
        raise ValueError(msg)

    names = [spec.name for spec in plan.parameter_space]
    value_lists = [
        _with_held(
            [
                _level(plan.declarations[spec.name], level)
                for level in enumerate_spec_values(spec)
            ],
            plan.fixed_parameters.get(spec.name),
        )
        for spec in plan.parameter_space
    ]
    variants: list[SweepVariantSpec] = []
    for idx, combo in enumerate(product(*value_lists)):
        sweep_values = dict(zip(names, combo, strict=True))
        params: dict[str, ParamValue] = {**plan.fixed_parameters, **sweep_values}
        variants.append(SweepVariantSpec(id=f"v{idx}", params=params))
    return variants


async def _evaluate_variant_wdk(
    variant: SweepVariantSpec,
    target: SweepTarget,
    controls: SweepControls,
) -> tuple[ControlTestResult | None, str]:
    """Run a single WDK control-test evaluation for ``variant``.

    Returns ``(result, error_string)``. ``result`` is ``None`` when WDK
    refused the call; the caller propagates the error string into the
    :class:`SweepVariantResult`.
    """
    config = IntersectionConfig(
        site_id=target.site_id,
        record_type=target.record_type,
        target_search_name=target.search_name,
        target_parameters=variant.params,
        controls_search_name=controls.controls_search_name,
        controls_param_name=controls.controls_param_name,
        controls_value_format=controls.controls_value_format,
        controls_extra_parameters=controls.controls_extra_parameters,
        id_field=controls.id_field,
        internal_strategy_name=CONTROL_TEST_STRATEGY_NAME,
    )
    try:
        wdk_result = await run_positive_negative_controls(
            config,
            positive_controls=controls.positive_controls,
            negative_controls=controls.negative_controls,
        )
    except VEuPathDBError as exc:
        return None, str(exc)
    return wdk_result, ""


async def run_trial(
    variant: SweepVariantSpec,
    *,
    target: SweepTarget,
    controls: SweepControls,
    score_cfg: OptimizationConfig,
    progress_callback: ProgressFn | None = None,
) -> SweepVariantResult:
    """Evaluate a single variant against the controls and return a typed result.

    Public entry point for parallel sweep workers. Issues exactly one
    WDK call per variant (no Bayesian state), computes the configured
    score from the controls intersection, and emits two progress events:
    ``percent=0.05`` at start and ``percent=1.0`` on completion.

    On WDK failure the returned :class:`SweepVariantResult` carries
    ``status="failed"`` and ``error`` populated; the caller decides
    whether to count it as fan-out failure (the impl wraps catastrophic
    exceptions one level up).
    """
    if progress_callback is not None:
        await progress_callback(
            0.05,
            f"Evaluating variant {variant.id}",
            {"params": to_decoded_map(variant.params)},
        )

    wdk_result, wdk_error = await _evaluate_variant_wdk(variant, target, controls)

    if wdk_result is None:
        if progress_callback is not None:
            await progress_callback(
                1.0,
                f"Variant {variant.id} WDK error",
                {"error": wdk_error},
            )
        return SweepVariantResult(
            variant_id=variant.id,
            status="failed",
            params=variant.params,
            error=wdk_error or "WDK evaluation returned no result",
        )

    metrics = _extract_trial_metrics(wdk_result)
    score = _compute_score(metrics, score_cfg, estimated_size=metrics.estimated_size)
    result = SweepVariantResult(
        variant_id=variant.id,
        status="success",
        params=variant.params,
        score=score,
        recall=metrics.recall,
        false_positive_rate=metrics.fpr,
        estimated_size=metrics.estimated_size,
        positive_hits=metrics.positive_hits,
        negative_hits=metrics.negative_hits,
        positive=wdk_result.positive,
        negative=wdk_result.negative,
    )
    if progress_callback is not None:
        await progress_callback(
            1.0,
            f"Variant {variant.id} score={'none' if score is None else f'{score:.4f}'}",
            {"score": score},
        )
    return result
