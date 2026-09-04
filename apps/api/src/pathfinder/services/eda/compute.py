"""Compute orchestration: submit, poll, read, and threshold."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from assistant_core.platform.pydantic_base import CamelModel

from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.integrations.eda.errors import EdaError
from pathfinder.integrations.eda.factory import get_eda_client
from pathfinder.integrations.eda.models import (
    EdaAnalysisDetail,
    EdaComputation,
    EdaComputationDescriptor,
    EdaComputeJob,
    EdaDifferentialExpressionConfig,
    EdaFilter,
    EdaJobStatus,
    VolcanoStatsResponse,
    VolcanoStatsRow,
)
from pathfinder.platform.errors import AppError, ErrorCode
from pathfinder.services.eda.authoring import apply_computation
from pathfinder.services.eda.binding import read_analysis
from pathfinder.services.eda.catalog import resolve_dataset

_CONFLICT = 409

TERMINAL_STATUSES: frozenset[EdaJobStatus] = frozenset(
    {"complete", "failed", "expired", "no-such-job"}
)
RUNNING_STATUSES: frozenset[EdaJobStatus] = frozenset({"queued", "in-progress"})


class NoComputationError(AppError):
    """The analysis carries no compute, so it has no volcano.

    The status is a conflict: the request is well formed and the analysis is
    not in a state that can answer it.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            code=ErrorCode.EDA_COMPUTE_NOT_RUN,
            title="No comparison has run",
            status=_CONFLICT,
            detail=detail,
        )


class VolcanoThresholds(CamelModel):
    """The volcano cut both surfaces and the export share."""

    effect_size_threshold: float
    significance_threshold: float
    effect_direction: EdaEffectDirection = "upAndDown"


@dataclass(frozen=True, slots=True)
class RetainedSummary:
    """How many points pass the thresholds, and how many could not be read."""

    total_rows: int
    unparseable_rows: int
    retained: int
    retained_up: int
    retained_down: int


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _numbers(row: VolcanoStatsRow) -> tuple[float, float] | None:
    """The row's effect size and p-value, or None when either cannot be read."""
    effect = _as_float(row.effect_size)
    p_value = _as_float(row.p_value)
    if effect is None or p_value is None:
        return None
    return effect, p_value


def _retained(
    stats: VolcanoStatsResponse,
    *,
    effect_size_threshold: float,
    significance_threshold: float,
    effect_direction: str,
) -> Iterator[tuple[VolcanoStatsRow, float]]:
    for row in stats.statistics:
        numbers = _numbers(row)
        if numbers is None:
            continue
        effect, p_value = numbers
        if abs(effect) < effect_size_threshold:
            continue
        if p_value > significance_threshold:
            continue
        if effect_direction == "upOnly" and effect <= 0:
            continue
        if effect_direction == "downOnly" and effect >= 0:
            continue
        yield row, effect


def retained_summary(
    stats: VolcanoStatsResponse,
    *,
    effect_size_threshold: float,
    significance_threshold: float,
    effect_direction: str = "upAndDown",
) -> RetainedSummary:
    """Count the points the WDK step would deliver for these thresholds."""
    unparseable = sum(1 for row in stats.statistics if _numbers(row) is None)
    up = 0
    down = 0
    for _row, effect in _retained(
        stats,
        effect_size_threshold=effect_size_threshold,
        significance_threshold=significance_threshold,
        effect_direction=effect_direction,
    ):
        if effect > 0:
            up += 1
        else:
            down += 1
    return RetainedSummary(
        total_rows=len(stats.statistics),
        unparseable_rows=unparseable,
        retained=up + down,
        retained_up=up,
        retained_down=down,
    )


def retained_point_ids(
    stats: VolcanoStatsResponse,
    *,
    effect_size_threshold: float,
    significance_threshold: float,
    effect_direction: str = "upAndDown",
) -> list[str]:
    """The point ids that pass, in the order the service sent them."""
    return [
        row.point_id
        for row, _effect in _retained(
            stats,
            effect_size_threshold=effect_size_threshold,
            significance_threshold=significance_threshold,
            effect_direction=effect_direction,
        )
    ]


@dataclass(frozen=True, slots=True)
class VolcanoPoint:
    """One gene on the volcano, and whether this cut keeps it."""

    point_id: str
    effect_size: float
    p_value: float | None
    adjusted_p_value: float | None
    retained: bool


@dataclass(frozen=True, slots=True)
class VolcanoView:
    """Every readable point of one compute, marked against one cut."""

    effect_size_label: str
    total_points: int
    retained_points: int
    points: list[VolcanoPoint]


def volcano_view(
    stats: VolcanoStatsResponse,
    *,
    thresholds: VolcanoThresholds,
) -> VolcanoView:
    """The plot both surfaces draw.

    A row with no readable effect size has no x coordinate and is dropped. A
    row with no readable p-value keeps its place and never passes the cut.
    """
    kept = set(
        retained_point_ids(
            stats,
            effect_size_threshold=thresholds.effect_size_threshold,
            significance_threshold=thresholds.significance_threshold,
            effect_direction=thresholds.effect_direction,
        )
    )
    points = [
        VolcanoPoint(
            point_id=row.point_id,
            effect_size=effect,
            p_value=_as_float(row.p_value),
            adjusted_p_value=_as_float(row.adjusted_p_value),
            retained=row.point_id in kept,
        )
        for row in stats.statistics
        if (effect := _as_float(row.effect_size)) is not None
    ]
    return VolcanoView(
        effect_size_label=stats.effect_size_label,
        total_points=len(stats.statistics),
        retained_points=len(kept),
        points=points,
    )


_READ_ATTEMPTS = 3
_READ_BACKOFF_SECONDS = 2.0
_RETRYABLE_STATUS = 500


async def lookup_job(
    site_id: str,
    *,
    compute_name: str,
    study_id: str,
    config: EdaDifferentialExpressionConfig,
    filters: Sequence[EdaFilter],
) -> EdaComputeJob:
    """Ask whether this configuration has been computed, without starting it."""
    return await get_eda_client(site_id).submit_compute(
        compute_name=compute_name,
        study_id=study_id,
        config=config,
        filters=filters,
        autostart=False,
    )


async def submit_compute(
    site_id: str,
    *,
    compute_name: str,
    study_id: str,
    config: EdaDifferentialExpressionConfig,
    filters: Sequence[EdaFilter],
) -> EdaComputeJob:
    """Start the job, or adopt the one this configuration already addresses."""
    return await get_eda_client(site_id).submit_compute(
        compute_name=compute_name,
        study_id=study_id,
        config=config,
        filters=filters,
        autostart=True,
    )


def _records(
    analysis: EdaAnalysisDetail,
    computation: EdaComputationDescriptor,
) -> bool:
    """Whether the analysis already carries exactly this compute."""
    computations = analysis.descriptor.computations
    return len(computations) == 1 and computations[0].descriptor == computation


async def run_analysis_compute(
    site_id: str,
    *,
    analysis_id: str,
    dataset_id: str,
    computation: EdaComputationDescriptor,
) -> EdaComputeJob:
    """Record this compute on the analysis, then start the job that answers it.

    The analysis document is the SSOT every volcano reads, so a compute it
    does not carry is written there before any job starts, and a
    configuration the study rejects starts none. The identical call repeated
    is the status poll, and a poll writes nothing. The analysis holds one
    computation, so the analysis id names it.
    """
    entry = await resolve_dataset(site_id, dataset_id)
    analysis = await read_analysis(site_id, analysis_id=analysis_id)
    if not _records(analysis, computation):
        analysis = await apply_computation(
            site_id,
            analysis_id=analysis_id,
            dataset_id=dataset_id,
            computation=EdaComputation(
                computation_id=analysis_id,
                descriptor=computation,
            ),
        )
    return await submit_compute(
        site_id,
        compute_name=computation.type,
        study_id=entry.study_id,
        config=computation.configuration,
        filters=analysis.descriptor.subset.descriptor,
    )


async def poll_job(site_id: str, *, job_id: str) -> EdaComputeJob:
    """One status read. There is no push channel and no ETag."""
    return await get_eda_client(site_id).get_job(job_id)


async def read_statistics(
    site_id: str,
    *,
    compute_name: str,
    study_id: str,
    config: EdaDifferentialExpressionConfig,
    filters: Sequence[EdaFilter],
) -> VolcanoStatsResponse:
    """The completed job's statistics.

    A read right after completion can fail at the proxy, so a 5xx is retried
    and the last attempt raises whatever it raises.
    """
    client = get_eda_client(site_id)
    for attempt in range(_READ_ATTEMPTS - 1):
        try:
            return await client.compute_statistics(
                compute_name=compute_name,
                study_id=study_id,
                config=config,
                filters=filters,
            )
        except EdaError as exc:
            if exc.status < _RETRYABLE_STATUS:
                raise
            await asyncio.sleep(_READ_BACKOFF_SECONDS * (attempt + 1))
    return await client.compute_statistics(
        compute_name=compute_name,
        study_id=study_id,
        config=config,
        filters=filters,
    )


async def bound_volcano(
    site_id: str,
    *,
    dataset_id: str,
    analysis: EdaAnalysisDetail,
    thresholds: VolcanoThresholds,
) -> VolcanoView:
    """The volcano of this analysis's compute, marked against one cut.

    It never starts a job: a compute that has not run is a conflict.
    """
    if not analysis.descriptor.computations:
        msg = (
            f"Analysis {analysis.analysis_id} has no comparison yet; run the "
            f"differential expression first."
        )
        raise NoComputationError(msg)
    computation = analysis.descriptor.computations[0]
    entry = await resolve_dataset(site_id, dataset_id)
    statistics = await read_statistics(
        site_id,
        compute_name=computation.descriptor.type,
        study_id=entry.study_id,
        config=computation.descriptor.configuration,
        filters=analysis.descriptor.subset.descriptor,
    )
    return volcano_view(statistics, thresholds=thresholds)
