"""A run halted across stages resumes where its refused units are, a sign-in check the OAuth server
does not answer is waited for, and a start that dies between its writes is picked up again."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from assistant_core.models.scripted import terminal_call
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb.errors import ExternalServiceError, WDKLoginRequiredError
from veupathdb.wdk import VEuPathDBClaims

from pathfinder.ai.audit import review
from pathfinder.domain.audit.verdicts import ReviewProgress
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.services import wdk_identity
from pathfinder.services.audit import job
from pathfinder.services.audit.job import (
    outcome,
    resume_stranded_runs,
    start_run,
)
from pathfinder.services.audit.queue import audit_lock
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.services.audit.sign_in import seal_sign_in
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import (
    SCOPE,
    TOKEN,
    Checks,
    audit_jobs,
    holding,
    queued,
    registered,
    sealed,
    short_runs,
    split_finding,
    unanswered,
    wire_checks,
    work,
    work_through,
)
from pathfinder.tests.integration.jobs._audit_reviews import work_reviews

SIGN_IN_NEEDED = "sign-in needed"
_OUTAGE = ExternalServiceError(
    "VEuPathDB OAuth", "the signing key read failed", status=503
)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Checks:
    return wire_checks(monkeypatch)


@pytest.fixture
def jobs(
    db_cleaner: None,
    patch_app_db_engine: None,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InMemoryConnector]:
    del db_cleaner, patch_app_db_engine
    registered(monkeypatch, TOKEN)
    with sealed_provider_keys(monkeypatch):
        yield in_memory_jobs
    get_settings.cache_clear()


def _oauth_down(monkeypatch: pytest.MonkeyPatch, times: int) -> list[str]:
    asked: list[str] = []

    async def _claims(token: str, oauth_url: str) -> VEuPathDBClaims | None:
        del oauth_url
        asked.append(token)
        if len(asked) <= times:
            raise _OUTAGE
        return VEuPathDBClaims(sub="1248677203", is_guest=token != TOKEN)

    monkeypatch.setattr(wdk_identity, "validate_oauth_token", _claims)
    return asked


async def test_a_halt_that_refused_units_of_a_finished_stage_reads_them_again(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.answered_first = 1
    wired.forbidden = 3
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    await work_through(jobs)

    halted = await owned_run(run_id, owner)
    assert (halted.stages.halted, halted.stages.next_stage) == (
        SIGN_IN_NEEDED,
        "confirm",
    )
    with holding(TOKEN):
        await start_run(run_id, owner)
    await work_through(jobs)

    done = await outcome(run_id, owner)
    assert (done.phase, done.halted) == ("finished", None)
    assert (done.counts.screened, done.counts.failed, done.counts.confirmed) == (
        0,
        0,
        3,
    )


async def test_a_resume_during_an_oauth_outage_waits_with_the_sign_in_kept(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    for queued_job in audit_jobs(jobs):
        del jobs.jobs[queued_job["id"]]
    async with async_session_factory() as session:
        await AuditRepository(session).set_status(run_id, "running")
        await session.commit()
    asked = _oauth_down(monkeypatch, times=1)

    await resume_stranded_runs()
    (first,) = queued(jobs)
    await work(jobs, first)

    waiting = await owned_run(run_id, owner)
    assert (waiting.status, waiting.stages.halted) == ("running", None)
    assert await sealed(run_id) is not None
    (later,) = queued(jobs)
    assert (later["args"]["payload"]["pause"], later["lock"]) == (
        60.0,
        audit_lock(run_id),
    )
    assert wired.site.genome_reads == []

    await work(jobs, later)

    assert len(asked) == 2
    assert (await owned_run(run_id, owner)).status == "finished"
    assert await sealed(run_id) is None


async def test_a_refused_start_erases_the_kept_sign_in_and_leaves_a_finished_run_alone(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    del wired
    owner = await seed_thread()
    stranded = await create_run(owner=owner, scope=SCOPE)
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.set_status(stranded, "running")
        await repo.set_token(stranded, seal_sign_in(stranded, owner.user_id, TOKEN))
        await session.commit()
    with holding(None), pytest.raises(WDKLoginRequiredError):
        await start_run(stranded, owner)
    assert (await owned_run(stranded, owner)).stages.halted == SIGN_IN_NEEDED
    assert await sealed(stranded) is None

    finished = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(finished, owner)
    await work_through(jobs)
    await work_reviews(jobs)
    with holding(None), pytest.raises(WDKLoginRequiredError):
        await start_run(finished, owner, retry_unreached=True)
    assert (await outcome(finished, owner)).halted is None


async def test_a_unit_the_job_stopped_on_keeps_why_while_it_waits_to_be_read_again(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.pseudogene_crashes = 1
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    with pytest.raises(RuntimeError):
        await work(jobs, queued(jobs)[0])
    async with async_session_factory() as session:
        (piga,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(checks=("pseudogene_call",))
        )
    assert (piga.status, piga.message) == (
        "trying",
        "the audit job failed: RuntimeError: a library bug",
    )


async def test_a_planned_run_whose_job_was_never_queued_is_queued_by_a_resume(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _lost(queued_job: job.AuditJob, *, after: float) -> None:
        del queued_job, after

    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with monkeypatch.context() as patched:
        patched.setattr(job, "_defer", _lost)
        with holding(TOKEN):
            await start_run(run_id, owner)
    assert (await owned_run(run_id, owner)).status == "planned"
    assert queued(jobs) == []

    await resume_stranded_runs()
    await work_through(jobs)

    assert (await owned_run(run_id, owner)).status == "finished"
    assert wired.site.tokens == {TOKEN}


async def test_a_retry_that_fails_before_its_deadline_is_written_reopens_nothing(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.split_failures.append(unanswered())
    short_runs(monkeypatch)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    await work_through(jobs)
    await work_reviews(jobs)
    assert (await split_finding(run_id)).status == "unreached"

    async def _broken(
        self: AuditRepository, run_id: UUID, deadline_at: datetime
    ) -> None:
        del self, run_id, deadline_at
        msg = "the database went away"
        raise RuntimeError(msg)

    monkeypatch.setattr(AuditRepository, "set_deadline", _broken)
    with holding(TOKEN), pytest.raises(RuntimeError, match="went away"):
        await start_run(run_id, owner, retry_unreached=True)

    assert (await owned_run(run_id, owner)).status == "finished"
    assert (await split_finding(run_id)).status == "unreached"


def _refusing(called: list[int]) -> FunctionModel:
    def refuse(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        called.append(1)
        return ModelResponse(parts=[terminal_call({})])

    return FunctionModel(refuse)


async def test_a_retry_clears_the_synthesis_and_a_stopped_one_leaves_none(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.split_failures.append(unanswered())
    short_runs(monkeypatch)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    await work_through(jobs)
    await work_reviews(jobs)
    assert (await owned_run(run_id, owner)).synthesis is not None

    with holding(TOKEN):
        await start_run(run_id, owner, retry_unreached=True)
    retrying = await owned_run(run_id, owner)
    assert (retrying.status, retrying.synthesis, retrying.review) == (
        "running",
        None,
        ReviewProgress(status="waiting"),
    )

    called: list[int] = []
    monkeypatch.setattr(review, "synthesis_model", lambda model_id: _refusing(called))
    await work_through(jobs)
    await work_reviews(jobs)

    run = await owned_run(run_id, owner)
    assert run.review is not None
    assert (run.status, run.synthesis, run.review.status, bool(called)) == (
        "finished",
        None,
        "stopped",
        True,
    )


async def test_an_unanswered_check_near_the_deadline_waits_to_the_deadline_unread(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    short_runs(monkeypatch)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    asked = _oauth_down(monkeypatch, times=10)
    started = datetime.now(UTC)

    await work(jobs, queued(jobs)[0])

    run = await owned_run(run_id, owner)
    assert run.deadline_at is not None
    assert (run.stages.halted, await sealed(run_id) is not None) == (None, True)
    (later,) = queued(jobs)
    assert later["scheduled_at"] <= run.deadline_at + timedelta(seconds=1)
    assert later["scheduled_at"] < started + timedelta(seconds=30)
    assert wired.site.genome_reads == []

    jobs.jobs[later["id"]]["args"]["payload"]["deadline"] = (
        started - timedelta(seconds=1)
    ).isoformat()
    await work(jobs, later)

    done = await outcome(run_id, owner)
    assert (done.phase, done.halted, len(asked)) == ("finished", None, 2)
    assert (wired.site.genome_reads, wired.asked) == ([], [])
    assert len(done.unread_genomes) == 10
