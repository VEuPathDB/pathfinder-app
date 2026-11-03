"""One compute job driven to a terminal status, with progress, for every plugin."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.eda import EdaComputeConfig, EdaComputeJob, EdaFilter

from pathfinder.services.eda.compute import (
    RUNNING_STATUSES,
    lookup_job,
    poll_job,
    submit_compute,
)

POLL_SECONDS = 3.0
MAX_POLLS = 200

# A queued job has no position most of the time, so the percent is a floor
# rather than a measurement: the poll count moves it, never past the ceiling.
_QUEUED_PERCENT = 0.1
_RUNNING_CEILING = 0.85


def _submit_message(job: EdaComputeJob) -> str:
    if job.status != "queued":
        return "Starting the compute"
    if job.queue_position is None:
        return "The job is queued"
    return f"The job is queued at position {job.queue_position}"


def _running_message(job: EdaComputeJob) -> str:
    if job.status == "queued":
        return _submit_message(job)
    return "The compute is running"


def _running_percent(polls: int) -> float:
    return _QUEUED_PERCENT + (_RUNNING_CEILING - _QUEUED_PERCENT) * polls / MAX_POLLS


async def settled_job(
    site_id: str,
    *,
    compute_name: str,
    study_id: str,
    config: EdaComputeConfig,
    filters: Sequence[EdaFilter],
    progress: TaskProgressEmitter,
) -> EdaComputeJob:
    """The job for this configuration, driven to a terminal status."""
    await progress.update(percent=0.0, message="Checking for a cached result")
    job = await lookup_job(
        site_id,
        compute_name=compute_name,
        study_id=study_id,
        config=config,
        filters=filters,
    )
    if job.status == "complete":
        return job
    await progress.update(percent=_QUEUED_PERCENT, message=_submit_message(job))
    job = await submit_compute(
        site_id,
        compute_name=compute_name,
        study_id=study_id,
        config=config,
        filters=filters,
    )
    polls = 0
    while job.status in RUNNING_STATUSES and polls < MAX_POLLS:
        await progress.update(
            percent=_running_percent(polls),
            message=_running_message(job),
        )
        await asyncio.sleep(POLL_SECONDS)
        job = await poll_job(site_id, job_id=job.job_id)
        polls += 1
    return job


def refusal_of(
    job: EdaComputeJob, *, job_name: str, stated: str | None = None
) -> RuntimeError:
    """Why a job that did not complete yields no result.

    The log of a failed job names no cause. ``stated`` is what else is known of the job.
    """
    match job.status:
        case "failed":
            known = f" {stated}" if stated else ""
            return RuntimeError(
                f"The {job_name} job {job.job_id} is failed. The site's compute "
                f"service publishes no reason for a failed job, so the cause is "
                f"not known.{known} A job id is a hash of the request and the "
                f"service does not run a failed job again, so the same arguments "
                f"return this same job."
            )
        case "expired":
            meaning = "the result is gone and the job needs a resubmit"
        case "no-such-job":
            meaning = "the inputs changed, so no job addresses them"
        case _:
            meaning = f"the job did not settle in {MAX_POLLS} polls"
    return RuntimeError(f"The {job_name} job {job.job_id} is {job.status}: {meaning}.")


__all__ = ["MAX_POLLS", "POLL_SECONDS", "refusal_of", "settled_job"]
