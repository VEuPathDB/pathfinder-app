"""The periodic resume pass queues a job for every run that lost its job, and never a second one."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector

from pathfinder.jobs.tasks import resume_stranded_audits_job
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.platform.config import get_settings
from pathfinder.services.audit.job import audit_lock, start_run
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
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
    wire_checks,
    work,
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
    with sealed_provider_keys(monkeypatch), holding(TOKEN):
        yield in_memory_jobs
    get_settings.cache_clear()


async def _running(*run_ids: UUID) -> None:
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        for run_id in run_ids:
            await repo.set_status(run_id, "running")
        await session.commit()


async def _stranded(jobs: InMemoryConnector, owner: RunOwner) -> UUID:
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    for job in audit_jobs(jobs):
        if job["lock"] == audit_lock(run_id):
            del jobs.jobs[job["id"]]
    await _running(run_id)
    return run_id


async def test_one_pass_queues_every_running_run_that_lost_its_job(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    owner = await seed_thread()
    stranded = await _stranded(jobs, owner)
    queued_run, halted, finished = [
        await create_run(owner=owner, scope=SCOPE) for _ in range(3)
    ]
    for run_id in (queued_run, halted, finished):
        await start_run(run_id, owner)
    for job in audit_jobs(jobs):
        if job["lock"] != audit_lock(queued_run):
            del jobs.jobs[job["id"]]
    await _running(queued_run, halted)
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.set_halted(halted, "sign-in needed")
        await repo.set_status(finished, "finished")
        await session.commit()

    await resume_stranded_audits_job(timestamp=0)

    assert sorted(j["lock"] for j in queued(jobs)) == sorted(
        [audit_lock(stranded), audit_lock(queued_run)]
    )
    (resumed,) = [j for j in queued(jobs) if j["lock"] == audit_lock(stranded)]
    run = await owned_run(stranded, owner)
    assert run.deadline_at is not None
    assert resumed["args"]["payload"]["pause"] == 30.0
    assert resumed["args"]["payload"][
        "deadline"
    ] == run.deadline_at.isoformat().replace("+00:00", "Z")
    await work(jobs, resumed)
    assert (await owned_run(stranded, owner)).status == "finished"
    assert wired.site.tokens == {TOKEN}


async def test_two_passes_queue_one_job_for_a_stranded_run(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    del wired
    run_id = await _stranded(jobs, await seed_thread())

    await resume_stranded_audits_job(timestamp=0)
    await resume_stranded_audits_job(timestamp=300)

    assert [j["lock"] for j in audit_jobs(jobs)] == [audit_lock(run_id)]


async def test_a_pass_while_the_runs_job_is_queued_queues_nothing_more(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    del wired
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    (started,) = audit_jobs(jobs)
    await _running(run_id)

    await resume_stranded_audits_job(timestamp=0)

    assert [j["id"] for j in audit_jobs(jobs)] == [started["id"]]


async def test_a_pass_while_the_runs_job_is_doing_queues_nothing(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    del wired
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    (started,) = audit_jobs(jobs)
    jobs.jobs[started["id"]]["status"] = "doing"
    await _running(run_id)

    await resume_stranded_audits_job(timestamp=0)

    assert [(j["id"], j["status"]) for j in audit_jobs(jobs)] == [
        (started["id"], "doing")
    ]
