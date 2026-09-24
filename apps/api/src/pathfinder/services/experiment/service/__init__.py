"""Experiment execution orchestrator.

Coordinates the experiment lifecycle: evaluation, then the stored result.
Each phase is a function under ``phases/``.
"""

import time
from datetime import UTC, datetime
from uuid import uuid4

from pathfinder.platform.errors import sanitize_error_for_client
from pathfinder.services.experiment.service.context import PhaseContext
from pathfinder.services.experiment.service.phases.evaluate import phase_evaluate
from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.experiment.types import Experiment, ExperimentConfig


async def run_experiment(
    config: ExperimentConfig,
    *,
    user_id: str | None = None,
) -> Experiment:
    """Execute a full experiment and persist the result.

    :param config: Experiment configuration.
    :param user_id: Owning user ID (for IDOR protection).
    :returns: Completed experiment with all results.
    """
    store = get_experiment_store()
    experiment = Experiment(
        id=f"exp_{uuid4().hex[:12]}",
        config=config,
        user_id=user_id,
        status="running",
        created_at=datetime.now(UTC).isoformat(),
    )
    store.save(experiment)
    start = time.monotonic()
    pctx = PhaseContext(config=config, experiment=experiment, store=store)
    try:
        await phase_evaluate(pctx)

        experiment.status = "completed"
        experiment.total_time_seconds = time.monotonic() - start
        experiment.completed_at = datetime.now(UTC).isoformat()
        store.save(experiment)
    except Exception as exc:
        experiment.status = "error"
        experiment.error = sanitize_error_for_client(exc)
        experiment.total_time_seconds = time.monotonic() - start
        store.save(experiment)
        raise
    else:
        return experiment
