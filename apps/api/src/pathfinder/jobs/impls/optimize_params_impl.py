from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import UUID

from assistant_core.memory.store import MemoryStore
from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from pydantic import JsonValue

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.tools.standalone._optimization_models import (
    OptimizationControls,
    OptimizationSettings,
    OptimizationTarget,
    _attach_export,
    _parse_and_validate_inputs,
)
from pathfinder.domain.parameters.optimization import (
    SweepResult,
    VariantResult,
    VariantSpec,
)
from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.services.experiment.types import (
    ControlValueFormat,
    OptimizationObjective,
)
from pathfinder.services.parameter_optimization.config import OptimizationConfig
from pathfinder.services.parameter_optimization.sweep import (
    SweepControls,
    SweepTarget,
    enumerate_variants,
    run_trial,
)

logger = get_logger(__name__)

# Default fan-out cap when the caller does not pin ``max_parallel``. Five
# matches the WDK-friendly batch size used elsewhere and keeps a sweep of
# typical 5-15 variants from oversubscribing the upstream service.
_DEFAULT_MAX_PARALLEL = 5


async def run_single_trial(
    variant: VariantSpec,
    *,
    progress: TaskProgressEmitter,
    context: Context,
    target: SweepTarget,
    controls: SweepControls,
    score_cfg: OptimizationConfig,
) -> dict[str, Any]:
    """Run a single variant trial and return its serialised result.

    Module-level so tests can ``monkeypatch.setattr`` it without touching
    the orchestrator. In production the body delegates to
    :func:`run_trial` in the service layer; the impl wraps the typed
    result back into a JSON-serialisable dict for the durable task row.
    """
    del context

    async def _on_progress(
        pct: float, msg: str, data: dict[str, JsonValue] | None
    ) -> None:
        await progress.update(percent=pct, message=msg, data=data)

    result = await run_trial(
        variant,
        target=target,
        controls=controls,
        score_cfg=score_cfg,
        progress_callback=_on_progress,
    )
    return result.model_dump(by_alias=True, mode="json")


async def optimize_search_parameters_impl(
    *,
    context: Context,
    task_id: UUID,
    progress: TaskProgressEmitter,
    memory_store: MemoryStore | None,
    target: dict[str, Any] | OptimizationTarget,
    controls: dict[str, Any] | OptimizationControls,
    settings: dict[str, Any] | OptimizationSettings | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """Run a parallel parameter sweep and return ``SweepResult`` as JSON.

    Builds the Cartesian variant grid from ``target.parameter_space``,
    fans out via ``asyncio.gather`` bounded by a Semaphore, and tags
    every per-variant progress event with ``variantId`` so the UI can
    render one lane per variant. One variant raising does NOT abort the
    others — each gated wrapper converts the exception into a
    ``status="failed"`` :class:`VariantResult`.
    """
    del task_id, memory_store

    progress.batch_size = 8

    target_m = (
        target
        if isinstance(target, OptimizationTarget)
        else OptimizationTarget.model_validate(target)
    )
    controls_m = (
        controls
        if isinstance(controls, OptimizationControls)
        else OptimizationControls.model_validate(controls)
    )
    settings_m = (
        settings
        if isinstance(settings, OptimizationSettings)
        else OptimizationSettings.model_validate(settings or {})
    )

    specs, fixed_parameters, controls_extra_parameters = _parse_and_validate_inputs(
        target_m, controls_m
    )

    sweep_target = SweepTarget(
        site_id=context.site_id,
        record_type=target_m.record_type,
        search_name=target_m.search_name,
        fixed_parameters=fixed_parameters,
    )
    sweep_controls = SweepControls(
        controls_search_name=controls_m.controls_search_name,
        controls_param_name=controls_m.controls_param_name,
        controls_value_format=cast(
            "ControlValueFormat", controls_m.controls_value_format
        ),
        controls_extra_parameters=controls_extra_parameters,
        positive_controls=controls_m.positive_controls or None,
        negative_controls=controls_m.negative_controls or None,
        id_field=controls_m.id_field,
    )
    score_cfg = OptimizationConfig(
        objective=cast("OptimizationObjective", settings_m.objective),
        beta=settings_m.beta,
        estimated_size_penalty=max(0.0, settings_m.estimated_size_penalty),
    )

    variants = enumerate_variants(specs, fixed_parameters)

    start_data: dict[str, JsonValue] = {
        "search_name": target_m.search_name,
        "variant_count": len(variants),
        "objective": settings_m.objective,
    }
    if settings_m.criterion:
        start_data["criterion"] = settings_m.criterion
    if settings_m.model_id:
        start_data["model_id"] = settings_m.model_id
    await progress.update(
        percent=0.0,
        message=(
            f"Starting parallel sweep ({len(variants)} variants)"
            + (f" — {settings_m.criterion}" if settings_m.criterion else "")
        ),
        data=start_data,
    )

    cap = settings_m.max_parallel or _DEFAULT_MAX_PARALLEL
    sem = asyncio.Semaphore(cap)

    async def gated(v: VariantSpec) -> dict[str, Any]:
        scoped = progress.scoped(variantId=v.id)
        async with sem:
            try:
                return await run_single_trial(
                    v,
                    progress=scoped,
                    context=context,
                    target=sweep_target,
                    controls=sweep_controls,
                    score_cfg=score_cfg,
                )
            except Exception as exc:
                logger.exception(
                    "variant trial failed",
                    variant_id=v.id,
                    error=str(exc),
                )
                await scoped.update(
                    percent=1.0,
                    message=f"Variant {v.id} failed: {exc}",
                )
                return VariantResult(
                    variant_id=v.id,
                    status="failed",
                    params=v.params,
                    error=str(exc) or exc.__class__.__name__,
                ).model_dump(by_alias=True, mode="json")
            finally:
                # Per-variant child has its own buffer; without an explicit
                # flush here partial batches would never persist (the parent
                # owns a different buffer and cannot drain children).
                await scoped.aclose()

    raw_results = await asyncio.gather(*(gated(v) for v in variants))

    sweep = SweepResult.model_validate({"variants": raw_results, "best": None})
    result_json: dict[str, Any] = sweep.model_dump(by_alias=True, mode="json")
    result_json["objective"] = settings_m.objective
    if settings_m.criterion:
        result_json["criterion"] = settings_m.criterion
    if settings_m.model_id:
        result_json["modelId"] = settings_m.model_id

    await progress.update(
        percent=0.98,
        message="Exporting sweep result",
        data=None,
    )
    await _attach_export(cast("JSONObject", result_json), target_m.search_name)
    await progress.update(
        percent=1.0,
        message="Sweep complete",
        data=None,
    )
    await progress.flush()
    return result_json
