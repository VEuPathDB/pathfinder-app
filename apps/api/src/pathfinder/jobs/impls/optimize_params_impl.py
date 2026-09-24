from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from assistant_core.memory.store import MemoryStore
from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from assistant_core.tasks.progress import TaskProgressEmitter
from pydantic import JsonValue
from veupathdb.wdk import get_strategy_api

from pathfinder.ai.graph.runtime import Context
from pathfinder.services.evidence.optimization import (
    enumerate_variants,
    run_trial,
    sweep_plan_for_step,
)
from pathfinder.services.export.control_downloads import attach_sweep_download
from pathfinder.services.parameter_optimization.config import (
    SWEEP_BUDGET,
    OptimizationConfig,
    SweepControls,
    SweepResult,
    SweepTarget,
    SweepVariantResult,
    SweepVariantSpec,
)

logger = get_logger(__name__)

# Default fan-out cap. Five matches the WDK-friendly batch size used elsewhere
# and keeps a sweep of typical 5-15 variants from oversubscribing WDK.
MAX_PARALLEL = 5

# Controls are intersected the way the control-test tool intersects them.
_CONTROLS_SEARCH = "GeneByLocusTag"
_CONTROLS_PARAM = "ds_gene_ids"


async def run_single_trial(
    variant: SweepVariantSpec,
    *,
    progress: TaskProgressEmitter,
    context: Context,
    target: SweepTarget,
    controls: SweepControls,
    score_cfg: OptimizationConfig,
) -> dict[str, Any]:
    """Run a single variant trial and return its serialised result.

    Module-level so tests can ``monkeypatch.setattr`` it without touching
    the orchestrator.
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
    wdk_step_id: int,
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
    parameters: list[str] | None = None,
    budget: int = SWEEP_BUDGET,
    **_extra: Any,
) -> dict[str, Any]:
    """Sweep the parameters of a built step and return ``SweepResult`` as JSON.

    The step names the search, its own values are what every variant holds
    fixed, and the grid comes from the catalog's parameter metadata. One
    variant raising does NOT abort the others - each gated wrapper converts
    the exception into a ``status="failed"`` :class:`SweepVariantResult`.
    """
    del task_id, memory_store

    if not positive_controls and not negative_controls:
        msg = "At least one of positive_controls or negative_controls must be provided."
        raise ValueError(msg)

    progress.batch_size = 8

    step = await get_strategy_api(context.site_id).find_step(wdk_step_id)
    record_type = step.record_class_name or "transcript"
    plan = await sweep_plan_for_step(
        context.site_id,
        record_type,
        step.search_name,
        step.search_config.parameters,
        names=parameters,
        budget=budget,
    )

    sweep_target = SweepTarget(
        site_id=context.site_id,
        record_type=record_type,
        search_name=step.search_name,
        fixed_parameters=plan.fixed_parameters,
    )
    sweep_controls = SweepControls(
        controls_search_name=_CONTROLS_SEARCH,
        controls_param_name=_CONTROLS_PARAM,
        controls_value_format="newline",
        controls_extra_parameters={},
        positive_controls=positive_controls or None,
        negative_controls=negative_controls or None,
        id_field="primary_key",
    )
    score_cfg = OptimizationConfig()

    variants = enumerate_variants(plan.parameter_space, plan.fixed_parameters)

    await progress.update(
        percent=0.0,
        message=f"Starting parallel sweep ({len(variants)} variants)",
        data={
            "search_name": step.search_name,
            "variant_count": len(variants),
            "swept_parameters": [spec.name for spec in plan.parameter_space],
        },
    )

    sem = asyncio.Semaphore(MAX_PARALLEL)

    async def gated(v: SweepVariantSpec) -> dict[str, Any]:
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
                return SweepVariantResult(
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
    result_json: JSONObject = sweep.model_dump(by_alias=True, mode="json")
    result_json["objective"] = score_cfg.objective

    await progress.update(percent=0.98, message="Exporting sweep result", data=None)
    await attach_sweep_download(result_json, step.search_name)
    await progress.update(percent=1.0, message="Sweep complete", data=None)
    await progress.flush()
    return dict(result_json)
