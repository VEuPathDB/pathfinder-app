"""What ends a review job early: a failure, a stopped reviewer run, a run that is not finished, and a review that could not be queued."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from assistant_core.models.scripted import terminal_call
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import PaidBy
from assistant_core.quota import get_period_totals
from procrastinate.testing import InMemoryConnector
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy.exc import OperationalError

from pathfinder.ai.audit import review
from pathfinder.domain.audit.verdicts import ReviewProgress
from pathfinder.jobs.impls.audit_review_impl import REVIEW_FAILED, run_review_job
from pathfinder.jobs.tasks import resume_stranded_audits_job
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.platform.config import get_settings
from pathfinder.services.audit import reviews
from pathfinder.services.audit.job import start_run
from pathfinder.services.audit.reviews import (
    defer_review,
    reviewed_run,
    start_review,
    stored_reviews,
)
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import (
    SCOPE,
    TOKEN,
    holding,
    registered,
    wire_checks,
    work_through,
)
from pathfinder.tests.integration.jobs._audit_reviews import (
    add_named,
    finished_run,
    gene,
    high,
    queued_reviews,
    recorded_reviewer,
    review_jobs,
    spent_tokens,
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
    registered(monkeypatch, TOKEN)
    with sealed_provider_keys(monkeypatch), holding(TOKEN):
        yield in_memory_jobs
    get_settings.cache_clear()


async def _progress(run_id: Any) -> ReviewProgress | None:
    run = await reviewed_run(run_id)
    assert run is not None
    return run.review


async def _fails(connector: InMemoryConnector, error: type[BaseException]) -> None:
    (job,) = queued_reviews(connector)
    connector.jobs[job["id"]]["status"] = "doing"
    with pytest.raises(error):
        await run_review_job(job["args"]["payload"])
    connector.jobs[job["id"]]["status"] = "failed"


def _answer(finding_id: int) -> dict[str, object]:
    return {
        "verdict": {
            "genes": [gene(1)],
            "modelGenome": "Examplea alpha A",
            "verdict": "error",
            "errorType": "truncated_model",
            "certainty": "high",
            "cause": "The relatives are longer.",
            "cites": [f"finding:{finding_id}"],
        },
        "alreadyKnown": "not_searched",
        "cardText": "A truncated synthetic model.",
    }


@pytest.mark.parametrize(
    ("failure", "named"),
    [
        (ModelHTTPError(status_code=500, model_name="mock:reviewer"), "ModelHTTPError"),
        (httpx.ConnectError("connection refused"), "ConnectError"),
    ],
)
async def test_a_failed_review_job_stops_with_its_reason_and_is_not_retried(
    jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    named: str,
) -> None:
    recorder = recorded_reviewer(monkeypatch)
    recorder.fail_at, recorder.failure = 1, failure
    _, run_id, _ = await finished_run({1: high(1), 2: high(2)})
    await defer_review(run_id)

    await _fails(jobs, type(failure))

    assert await _progress(run_id) == ReviewProgress(
        status="stopped", done=0, total=2, message=f"{REVIEW_FAILED}: {named}"
    )
    await resume_stranded_audits_job(timestamp=0)
    assert queued_reviews(jobs) == []


async def test_a_database_failure_stops_the_review_with_its_reason(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def lost(*args: object) -> None:
        del args
        statement = "INSERT INTO audit_verdicts"
        raise OperationalError(statement, {}, ConnectionError())

    monkeypatch.setattr(review, "store_review", lost)
    _, run_id, _ = await finished_run({1: high(1)})
    await defer_review(run_id)

    await _fails(jobs, OperationalError)

    assert await _progress(run_id) == ReviewProgress(
        status="stopped", done=0, total=1, message=f"{REVIEW_FAILED}: OperationalError"
    )
    await resume_stranded_audits_job(timestamp=0)
    assert queued_reviews(jobs) == []


async def test_the_tokens_of_a_run_that_fails_are_charged(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        calls.append(1)
        if len(calls) > 1:
            raise ModelHTTPError(status_code=503, model_name="test:reviewer")
        return ModelResponse(parts=[terminal_call({"verdict": {}})])

    model = FunctionModel(answer, model_name="test:reviewer")
    monkeypatch.setattr(review, "review_model", lambda model_id: model)
    tokens = spent_tokens(monkeypatch)
    owner, run_id, _ = await finished_run({1: high(1)})
    await defer_review(run_id)

    await _fails(jobs, ModelHTTPError)

    async with async_session_factory() as session:
        paid = await get_period_totals(
            session, owner.user_id, paid_by=PaidBy.DEPLOYMENT
        )
    assert len(tokens) == 1
    assert tokens[0] > 0
    assert paid.tokens == tokens[0]
    assert await stored_reviews(run_id) == []


async def test_a_second_run_that_stops_leaves_no_second_verdict(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs: list[int] = []
    _, run_id, stored = await finished_run({1: high(1)})
    finding_id = stored[gene(1)]

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        if len(messages) == 1:
            runs.append(1)
        valid = len(runs) == 1
        return ModelResponse(
            parts=[terminal_call(_answer(finding_id) if valid else {"verdict": {}})]
        )

    model = FunctionModel(answer, model_name="test:reviewer")
    monkeypatch.setattr(review, "review_model", lambda model_id: model)
    await defer_review(run_id)

    await work_reviews(jobs)

    (found,) = await stored_reviews(run_id)
    assert found.review is not None
    assert (found.review.stopped, found.review.second_verdict) == (False, None)
    assert len(runs) == 2


async def test_a_first_run_that_stops_is_stored_stopped_and_not_judged_again(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = recorded_reviewer(monkeypatch)
    _, run_id, _ = await finished_run({1: high(1)})

    def malformed(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[terminal_call({"verdict": {}})])

    recorder.wrapped = FunctionModel(malformed, model_name="test:reviewer")
    await defer_review(run_id)

    await work_reviews(jobs)

    (found,) = await stored_reviews(run_id)
    assert found.review is not None
    assert (found.review.stopped, found.verdict.cause) == (True, review.OUT_OF_RETRIES)
    assert len(recorder.runs()) == 1


async def test_a_review_job_for_a_reopened_run_reviews_nothing(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = recorded_reviewer(monkeypatch)
    _, run_id, _ = await finished_run({1: high(1)})
    await defer_review(run_id)
    async with async_session_factory() as session:
        await AuditRepository(session).set_status(run_id, "running")
        await session.commit()

    assert await work_reviews(jobs) == 1

    assert (recorder.requests, await stored_reviews(run_id)) == ([], [])
    assert await _progress(run_id) == ReviewProgress(status="waiting")


async def test_a_resume_pass_queues_no_review_beside_a_doing_one(
    jobs: InMemoryConnector,
) -> None:
    _, run_id, _ = await finished_run({1: high(1)})
    await defer_review(run_id)
    (doing,) = review_jobs(jobs)
    jobs.jobs[doing["id"]]["status"] = "doing"

    await resume_stranded_audits_job(timestamp=0)

    assert [(j["id"], j["status"]) for j in review_jobs(jobs)] == [
        (doing["id"], "doing")
    ]


async def test_a_review_that_could_not_be_queued_leaves_the_run_finished_and_waiting(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    wire_checks(monkeypatch)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)

    async def refused(run_id: object) -> None:
        del run_id
        msg = "the queue refused the job"
        raise RuntimeError(msg)

    with monkeypatch.context() as patched:
        patched.setattr(reviews, "continue_review", refused)
        await work_through(jobs)

    run = await owned_run(run_id, owner)
    assert (run.status, run.stages.halted, run.review) == (
        "finished",
        None,
        ReviewProgress(status="waiting"),
    )
    assert review_jobs(jobs) == []
    await resume_stranded_audits_job(timestamp=0)
    assert len(queued_reviews(jobs)) == 1


async def test_a_retried_run_keeps_its_agreement_sample(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reviews, "AGREEMENT_SAMPLE", 1)
    owner, run_id, _ = await finished_run({1: high(1), 2: high(2)})
    await defer_review(run_id)
    await work_reviews(jobs)

    await add_named(run_id, {3: high(3), 4: high(4)})
    await start_review(run_id, owner)
    await work_reviews(jobs)

    found = await stored_reviews(run_id)
    paired = [v for v in found if v.review is not None and v.review.second_verdict]
    assert (len(found), len(paired)) == (4, 1)


async def test_a_retry_fills_only_the_sample_places_its_pairs_left(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reviews, "AGREEMENT_SAMPLE", 1)
    owner, run_id, _ = await finished_run({1: high(1), 2: high(2)})
    await defer_review(run_id)
    await work_reviews(jobs)
    monkeypatch.setattr(reviews, "AGREEMENT_SAMPLE", 2)

    await add_named(run_id, {3: high(3), 4: high(4), 5: high(5)})
    await start_review(run_id, owner)
    await work_reviews(jobs)

    found = await stored_reviews(run_id)
    paired = [v for v in found if v.review is not None and v.review.second_verdict]
    assert (len(found), len(paired)) == (5, 2)
