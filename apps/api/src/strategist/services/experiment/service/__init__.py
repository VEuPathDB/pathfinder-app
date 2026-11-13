"""Experiment execution orchestrator.

Coordinates the experiment lifecycle: evaluation, then the stored result.
Each phase is a function under ``phases/``.
"""

import time
from datetime import UTC, datetime
from uuid import uuid4

from strategist.platform.errors import sanitize_error_for_client
from strategist.services.experiment.service.context import PhaseContext
from strategist.services.experiment.service.phases.evaluate import phase_evaluate
from strategist.services.experiment.store import get_experiment_store
from strategist.services.experiment.types import Experiment, ExperimentConfig


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
    await store.save(experiment)
    start = time.monotonic()
    pctx = PhaseContext(config=config, experiment=experiment, store=store)
    try:
        await phase_evaluate(pctx)

        experiment.status = "completed"
        experiment.total_time_seconds = time.monotonic() - start
        experiment.completed_at = datetime.now(UTC).isoformat()
        await store.save(experiment)
    except Exception as exc:
        experiment.status = "error"
        experiment.error = sanitize_error_for_client(exc)
        experiment.total_time_seconds = time.monotonic() - start
        await store.save(experiment)
        raise
    else:
        return experiment
