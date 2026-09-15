"""Experiment store that serves an in-memory cache and writes every mutation
through to the database."""

from collections.abc import Iterable
from datetime import UTC, datetime
from functools import cache
from uuid import UUID

from assistant_core.platform.context import calling_application
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.store import WriteThruStore
from sqlalchemy import select

from pathfinder.persistence.models import ExperimentRow
from pathfinder.services.experiment._deserialize import experiment_from_json
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
        "batch_id": exp.batch_id,
        "benchmark_id": exp.benchmark_id,
        "gene_set_id": exp.config.gene_set_id,
        "created_at": _parse_created_at(exp.created_at),
    }


def _experiment_from_row(row: ExperimentRow) -> Experiment:
    """Reconstruct an experiment from a database row.

    The column carries the application, not the serialized blob, so a row
    written before the column existed reads as the application it belongs to.
    """
    experiment = experiment_from_json(row.data)
    return experiment.model_copy(update={"application_id": row.application_id})


def experiments_for_gene_set(
    experiments: Iterable[Experiment],
    *,
    gene_set_id: str,
    user_id: UUID,
) -> list[Experiment]:
    """The evaluations one user ran of one gene set, newest first.

    A batch or a benchmark child evaluates one slice of the set, never the set,
    so it is not an evaluation the set holds. The calling application owns the
    experiment with the user, so an experiment of another application never
    answers here.
    """
    application_id = calling_application()
    owned = [
        exp
        for exp in experiments
        if exp.config.gene_set_id == gene_set_id
        and exp.user_id == str(user_id)
        and exp.application_id == application_id
        and exp.batch_id is None
        and exp.benchmark_id is None
    ]
    owned.sort(key=lambda exp: _parse_created_at(exp.created_at), reverse=True)
    return owned


async def _list_from_db(gene_set_id: str, user_id: UUID) -> list[Experiment]:
    """The stored experiments the gene-set column points at this set."""
    stmt = select(ExperimentRow).where(
        ExperimentRow.gene_set_id == gene_set_id,
        ExperimentRow.user_id == user_id,
        ExperimentRow.application_id == calling_application(),
    )
    async with async_session_factory() as session:
        result = await session.execute(stmt)
        return [_experiment_from_row(row) for row in result.scalars().all()]


class ExperimentStore(WriteThruStore[Experiment]):
    """Experiment repository with an in-memory cache and database
    write-through. Every read answers only for the calling application."""

    _model = ExperimentRow
    _to_row = staticmethod(_row_from_experiment)
    _from_row = staticmethod(_experiment_from_row)

    async def aget(self, entity_id: str) -> Experiment | None:
        exp = await super().aget(entity_id)
        if exp is None or exp.application_id != calling_application():
            return None
        return exp

    async def alist_for_gene_set(
        self, gene_set_id: str, user_id: UUID
    ) -> list[Experiment]:
        """This user's evaluations of one gene set, newest first.

        The row write happens outside the caller's turn, so a run that just
        finished is in the cache before it is in the database.
        """
        merged = {exp.id: exp for exp in await _list_from_db(gene_set_id, user_id)}
        merged.update(self._cache)
        return experiments_for_gene_set(
            merged.values(), gene_set_id=gene_set_id, user_id=user_id
        )


@cache
def get_experiment_store() -> ExperimentStore:
    """Return the process-wide experiment store."""
    return ExperimentStore()
