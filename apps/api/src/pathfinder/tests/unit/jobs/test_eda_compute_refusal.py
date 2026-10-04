"""A job that did not complete is refused with what the site said about it."""

from __future__ import annotations

from veupathdb.eda import EdaComputeJob

from pathfinder.services.eda.compute_jobs import refusal_of

JOB_ID = "113dec29c65e6ad1b0c1707fa1549593"


def _message(status: str) -> str:
    job = EdaComputeJob.model_validate({"jobID": JOB_ID, "status": status})
    return str(refusal_of(job, job_name="differential-expression"))


def test_a_failed_job_says_the_site_gives_no_reason() -> None:
    assert _message("failed") == (
        f"The differential-expression job {JOB_ID} is failed. The site's compute "
        f"service publishes no reason for a failed job, so the cause is not known."
    )


def test_an_expired_job_names_the_resubmit() -> None:
    assert _message("expired") == (
        f"The differential-expression job {JOB_ID} is expired: the result is gone "
        f"and the job needs a resubmit."
    )


def test_a_job_that_did_not_settle_names_the_poll_budget() -> None:
    assert _message("in-progress") == (
        f"The differential-expression job {JOB_ID} is in-progress: the job did "
        f"not settle in 200 polls."
    )
