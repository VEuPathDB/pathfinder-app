"""An audit job's slice and deadline: it yields its slot, and what it never read is told apart from what the site left unanswered."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector

from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.audit import units
from pathfinder.services.audit.job import outcome, start_run
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import (
    SCOPE,
    TOKEN,
    Checks,
    holding,
    queued,
    registered,
    wire_checks,
    work,
    work_through,
)
from pathfinder.tests.integration.jobs._audit_reviews import work_reviews

_TOLERANCE = timedelta(seconds=5)


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


async def test_a_job_yields_its_slot_once_its_work_slice_is_spent(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    monkeypatch.setattr(units, "SLICE_SECONDS", 0.0)
    yielded_at = datetime.now(UTC)

    await work(jobs, queued(jobs)[0])

    (later,) = queued(jobs)
    assert wired.site.genome_reads == []
    assert later["args"]["payload"]["pause"] == 30.0
    assert abs(later["scheduled_at"] - yielded_at) < _TOLERANCE
    monkeypatch.setattr(units, "SLICE_SECONDS", 1800.0)
    assert await work_through(jobs) == 1
    assert (await owned_run(run_id, owner)).status == "finished"


async def test_units_a_late_continuation_never_read_are_stored_unread_and_retried(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    monkeypatch.setattr(units, "SLICE_SECONDS", 0.0)
    await work(jobs, queued(jobs)[0])
    monkeypatch.setattr(units, "SLICE_SECONDS", 1800.0)
    (later,) = queued(jobs)
    later["args"]["payload"]["deadline"] = datetime.now(UTC).isoformat()

    await work_through(jobs)

    async with async_session_factory() as session:
        states = await AuditRepository(session).genome_states(run_id)
    assert {(s.status, s.attempts, s.message) for s in states} == {
        ("unread", 0, units.NOT_READ)
    }
    assert wired.site.genome_reads == []
    (collect_stage, *_) = (await owned_run(run_id, owner)).stages.stages
    assert (collect_stage.done, collect_stage.total, collect_stage.message) == (
        0,
        10,
        "10 genomes not read before the run's deadline",
    )
    done = await outcome(run_id, owner)
    assert (done.status, len(done.unread_genomes), done.unreached_genomes) == (
        "finished",
        10,
        (),
    )
    await work_reviews(jobs)

    await start_run(run_id, owner, retry_unreached=True)
    await work_through(jobs)

    again = await outcome(run_id, owner)
    assert (again.status, again.unread_genomes, again.counts.confirmed) == (
        "finished",
        (),
        3,
    )
    assert len(wired.site.genome_reads) == 10


async def test_a_target_the_site_left_unanswered_stays_unreached_past_the_deadline(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.site.target_failures.append(httpx.ConnectError("connection refused"))
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    await work(jobs, queued(jobs)[0])
    (later,) = queued(jobs)
    assert (await owned_run(run_id, owner)).stages.next_stage == "screen"
    later["args"]["payload"]["deadline"] = datetime.now(UTC).isoformat()

    await work_through(jobs)

    async with async_session_factory() as session:
        (target,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(checks=("pseudogene_call",))
        )
    assert (target.status, target.attempts, target.message) == (
        "unreached",
        0,
        "connection refused",
    )
