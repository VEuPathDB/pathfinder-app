"""Experiment execution orchestrator.

Coordinates the full experiment lifecycle: evaluation, strategy persistence,
robustness, optional cross-validation, and optional enrichment analysis.
Each phase is a function in a dedicated submodule under ``phases/``.
"""

import time
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.services.experiment.helpers import ProgressCallback
from pathfinder.services.experiment.service.context import (
    PhaseContext,
    get_experiment_lock,
)
from pathfinder.services.experiment.service.phases.evaluate import (
    phase_evaluate,
    phase_persist_strategy,
)
from pathfinder.services.experiment.service.phases.validate import (
    phase_cross_validate,
    phase_enrich,
    phase_robustness,
)
from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.experiment.types import (
    Experiment,
    ExperimentConfig,
    ExperimentProgressPhase,
)

logger = get_logger(__name__)


async def run_experiment(
    config: ExperimentConfig,
    *,
    user_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Experiment:
    """Execute a full experiment and persist the result.

    :param config: Experiment configuration.
    :param user_id: Owning user ID (for IDOR protection).
    :param progress_callback: Optional async callback for SSE progress events.
    :returns: Completed experiment with all results.
    """
    experiment_id = f"exp_{uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()
    store = get_experiment_store()

    experiment = Experiment(
        id=experiment_id,
        config=config,
        user_id=user_id,
        status="running",
        created_at=now,
    )
    store.save(experiment)

    start = time.monotonic()

    async def _emit(phase: ExperimentProgressPhase, **extra: object) -> None:
        if progress_callback:
            event: JSONObject = {
                "type": "experiment_progress",
                "data": {
                    "experimentId": experiment_id,
                    "phase": phase,
                    **cast("JSONObject", dict(extra)),
                },
            }
            await progress_callback(event)

    experiment_lock = get_experiment_lock(experiment_id)
    await experiment_lock.acquire()
    try:
        await _emit("started", message="Starting evaluation...")

        pctx = PhaseContext(
            config=config,
            experiment=experiment,
            emit=_emit,
            store=store,
        )

        # Phase 1: Control-test evaluation + metrics + gene enrichment
        await phase_evaluate(pctx)

        plan_tree: StrategyStepNode | None = (
            config.step_tree if config.is_tree_mode else None
        )

        # Phase 2: Persist WDK strategy for result exploration
        await phase_persist_strategy(pctx, plan_tree)

        # Phase 3: Robustness / bootstrap CIs
        await phase_robustness(pctx)

        # Phase 4: Cross-validation
        if (
            config.enable_cross_validation
            and config.positive_controls
            and config.negative_controls
        ):
            await phase_cross_validate(pctx, plan_tree)

        # Phase 5: Enrichment analysis
        if config.enrichment_types:
            await phase_enrich(pctx)

        # Finalize
        experiment.status = "completed"
        experiment.total_time_seconds = time.monotonic() - start
        experiment.completed_at = datetime.now(UTC).isoformat()
        store.save(experiment)

        await _emit("completed", message="Experiment complete")

    except Exception as exc:
        experiment.status = "error"
        experiment.error = str(exc)
        experiment.total_time_seconds = time.monotonic() - start
        store.save(experiment)
        await _emit("error", error=str(exc))
        raise
    else:
        return experiment
    finally:
        experiment_lock.release()
