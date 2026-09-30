"""The experiment store: every save writes the ``experiments`` table."""

from datetime import UTC, datetime
from functools import cache

from assistant_core.platform.db import async_session_factory

from pathfinder.persistence.models import ExperimentRow
from pathfinder.persistence.repositories.experiment import ExperimentRepository
from pathfinder.services.experiment.types import (
    Experiment,
    experiment_to_json,
)


def _parse_created_at(iso_str: str) -> datetime:
    """Parse an ISO datetime string into a timezone-aware datetime."""
    if not iso_str:
        return datetime.now(UTC)
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _row_from_experiment(exp: Experiment) -> ExperimentRow:
    return ExperimentRow(
        id=exp.id,
        site_id=exp.config.site_id,
        user_id=exp.user_id,
        application_id=exp.application_id,
        name=exp.config.name or "",
        status=exp.status,
        data=experiment_to_json(exp),
        created_at=_parse_created_at(exp.created_at),
    )


class ExperimentStore:
    """Experiments, written to the database on every save."""

    async def save(self, experiment: Experiment) -> None:
        """Write the experiment's row, durable before the call returns."""
        async with async_session_factory() as session:
            await ExperimentRepository(session).put(_row_from_experiment(experiment))
            await session.commit()


@cache
def get_experiment_store() -> ExperimentStore:
    """Return the process-wide experiment store."""
    return ExperimentStore()
