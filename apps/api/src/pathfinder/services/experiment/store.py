"""Experiment store that serves an in-memory cache and writes every mutation
through to the database."""

from datetime import UTC, datetime
from functools import cache

from assistant_core.platform.store import WriteThruStore

from pathfinder.persistence.models import ExperimentRow
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


def _row_from_experiment(exp: Experiment) -> dict[str, object]:
    """Build the column values for an experiment row upsert."""
    return {
        "id": exp.id,
        "site_id": exp.config.site_id,
        "user_id": exp.user_id,
        "application_id": exp.application_id,
        "name": exp.config.name or "",
        "status": exp.status,
        "data": experiment_to_json(exp),
        "created_at": _parse_created_at(exp.created_at),
    }


def _experiment_from_row(row: ExperimentRow) -> Experiment:
    """Reconstruct an experiment from a database row.

    The column carries the application, not the serialized blob, so a row
    written before the column existed reads as the application it belongs to.
    """
    experiment = Experiment.model_validate(row.data)
    return experiment.model_copy(update={"application_id": row.application_id})


class ExperimentStore(WriteThruStore[Experiment]):
    """Experiment repository with an in-memory cache and database write-through."""

    _model = ExperimentRow
    _to_row = staticmethod(_row_from_experiment)
    _from_row = staticmethod(_experiment_from_row)


@cache
def get_experiment_store() -> ExperimentStore:
    """Return the process-wide experiment store."""
    return ExperimentStore()
