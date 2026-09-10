"""Evaluation phases: control-test evaluation and strategy persistence."""

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.errors import VEuPathDBError

from pathfinder.services.experiment.helpers import controls_context_from_config
from pathfinder.services.experiment.materialization import (
    _persist_experiment_strategy,
)
from pathfinder.services.experiment.metrics import (
    evaluate_gene_ids_against_controls,
)
from pathfinder.services.experiment.service.context import PhaseContext
from pathfinder.services.experiment.service.shared import (
    apply_control_result,
    run_single_step_controls,
)
from pathfinder.services.experiment.tree_evaluation import (
    run_controls_against_tree,
)

logger = get_logger(__name__)


async def phase_evaluate(pctx: PhaseContext) -> None:
    """Run control-test evaluation, compute metrics, and enrich gene lists."""
    config, experiment = pctx.config, pctx.experiment
    await pctx.emit("evaluating", message="Running control tests...")

    if config.target_gene_ids:
        # Gene set mode: evaluate using gene IDs directly, no WDK calls.

        result = evaluate_gene_ids_against_controls(
            gene_ids=config.target_gene_ids,
            positive_controls=config.positive_controls or [],
            negative_controls=config.negative_controls or [],
            site_id=config.site_id,
            record_type=config.record_type,
        )
    elif config.is_tree_mode and config.step_tree is not None:
        result = await run_controls_against_tree(
            controls_context_from_config(config),
            config.step_tree,
        )
    else:
        result = await run_single_step_controls(config, config.parameters)

    metrics = await apply_control_result(config, experiment, result)

    await pctx.emit(
        "evaluating",
        message="Evaluation complete",
        metrics=metrics.model_dump(by_alias=True),
    )
    pctx.store.save(experiment)


async def phase_persist_strategy(
    pctx: PhaseContext,
    final_tree: StrategyStepNode | None,
) -> None:
    """Create a persisted WDK strategy for result exploration (best-effort)."""
    config, experiment = pctx.config, pctx.experiment
    try:
        wdk_ids = await _persist_experiment_strategy(
            config,
            experiment.id,
            override_tree=final_tree,
        )
        raw_sid = wdk_ids.get("strategy_id")
        raw_step = wdk_ids.get("step_id")
        experiment.wdk_strategy_id = raw_sid if isinstance(raw_sid, int) else None
        experiment.wdk_step_id = raw_step if isinstance(raw_step, int) else None
        pctx.store.save(experiment)
    except (VEuPathDBError, RuntimeError) as exc:
        logger.warning(
            "Failed to persist WDK strategy for experiment",
            experiment_id=experiment.id,
            error=str(exc),
        )
