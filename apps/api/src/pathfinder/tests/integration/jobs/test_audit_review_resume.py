"""A review job that dies mid-run is queued again by the periodic resume pass and repeats no stored review."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from procrastinate.testing import InMemoryConnector

from pathfinder.domain.audit.verdicts import ReviewProgress
from pathfinder.jobs.impls.audit_review_impl import run_review_job
from pathfinder.jobs.tasks import resume_stranded_audits_job
from pathfinder.platform.config import get_settings
from pathfinder.services.audit import reviews
from pathfinder.services.audit.reviews import defer_review, reviewed_run, stored_reviews
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_reviews import (
    finished_run,
    high,
    queued_reviews,
    recorded_reviewer,
    work_reviews,
)


@pytest.fixture
def jobs(
    db_cleaner: None,
    patch_app_db_engine: None,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InMemoryConnector]:
    del db_cleaner, patch_app_db_engine
    with sealed_provider_keys(monkeypatch):
        yield in_memory_jobs
    get_settings.cache_clear()


async def test_a_killed_review_resumes_on_the_next_pass_without_repeating(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reviews, "AGREEMENT_SAMPLE", 1)
    recorder = recorded_reviewer(monkeypatch)
    _, run_id, stored = await finished_run({1: high(1), 2: high(2), 3: high(3)})
    run = await reviewed_run(run_id)
    assert run is not None
    sampled = await reviews.agreement_sample(run)
    recorder.fail_at = 3 if stored["EXA_0001"] in sampled else 2
    recorder.failure = asyncio.CancelledError()
    await defer_review(run_id)
    (killed,) = queued_reviews(jobs)
    jobs.jobs[killed["id"]]["status"] = "doing"

    with pytest.raises(asyncio.CancelledError):
        await run_review_job(killed["args"]["payload"])
    jobs.jobs[killed["id"]]["status"] = "failed"

    (first,) = await stored_reviews(run_id)
    left = await reviewed_run(run_id)
    assert left is not None
    assert left.review == ReviewProgress(status="reviewing", done=1, total=3)

    recorder.failure = None
    await resume_stranded_audits_job(timestamp=0)
    assert len(queued_reviews(jobs)) == 1
    assert await work_reviews(jobs) == 1

    found = await stored_reviews(run_id)
    assert found[0] == first
    assert sorted(v.finding_id or 0 for v in found) == sorted(stored.values())
    done = await reviewed_run(run_id)
    assert done is not None
    assert done.review == ReviewProgress(status="synthesized", done=3, total=3)
