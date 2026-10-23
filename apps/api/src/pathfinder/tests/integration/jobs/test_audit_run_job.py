"""An audit run on its own queue: one job per run at a time, four stages, waits off the worker, resumed and capped units."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from assistant_core.persistence.models import BackgroundTask
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.lease import advisory_lease
from procrastinate.testing import InMemoryConnector
from sqlalchemy import func, select

from pathfinder.domain.audit.findings import FindingCounts, RelativesEvidence
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.persistence.repositories.audit import STOPPED_MESSAGE, AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.audit.job import outcome, start_run
from pathfinder.services.audit.queue import AUDIT_QUEUE, audit_lock
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    PIGA,
    relative_organisms,
    seed_thread,
)
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import (
    SCOPE,
    SPLIT,
    TOKEN,
    Checks,
    audit_jobs,
    holding,
    queued,
    registered,
    sealed,
    short_runs,
    unanswered,
    wire_checks,
    work,
    work_through,
)

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


def _model_lengths(payloads: list[object]) -> list[int]:
    lengths: list[int] = []
    for payload in payloads:
        match payload:
            case RelativesEvidence(model_length=int() as length):
                lengths.append(length)
            case _:
                pass
    return sorted(lengths)


async def test_a_start_queues_one_job_on_the_audit_queue_and_no_task_row(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    del wired
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    asked_at = datetime.now(UTC)

    started = await start_run(run_id, owner)

    (job,) = audit_jobs(jobs)
    lock = audit_lock(run_id)
    assert (job["queue_name"], job["lock"], job["queueing_lock"]) == (
        AUDIT_QUEUE,
        lock,
        lock,
    )
    assert lock == f"audit-run:{run_id}"
    payload = job["args"]["payload"]
    run = await owned_run(run_id, owner)
    assert run.deadline_at is not None
    assert payload == {
        "run_id": str(run_id),
        "deadline": run.deadline_at.isoformat().replace("+00:00", "Z"),
        "pause": 30.0,
    }
    assert abs(run.deadline_at - (asked_at + timedelta(hours=6))) < _TOLERANCE
    assert (started.status, started.halted) == ("planned", None)
    kept = await sealed(run_id)
    assert kept is not None
    assert TOKEN.encode() not in kept
    async with async_session_factory() as session:
        rows = await session.scalar(select(func.count()).select_from(BackgroundTask))
    assert rows == 0


async def test_a_second_start_queued_running_or_at_once_makes_no_second_job(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    del wired
    owner = await seed_thread()
    first = await create_run(owner=owner, scope=SCOPE)
    second = await create_run(owner=owner, scope=SCOPE)

    await start_run(first, owner)
    await start_run(first, owner)
    (job,) = audit_jobs(jobs)
    jobs.jobs[job["id"]]["status"] = "doing"
    await start_run(first, owner)
    await asyncio.gather(start_run(second, owner), start_run(second, owner))

    assert Counter(j["lock"] for j in audit_jobs(jobs)) == Counter(
        {audit_lock(first): 1, audit_lock(second): 1}
    )


async def test_a_job_carries_a_run_through_four_stages_on_the_kept_sign_in(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)

    assert await work_through(jobs) == 1

    done = await outcome(run_id, owner)
    assert (done.status, done.release, done.requests, done.unfinished) == (
        "finished",
        "71",
        0,
        (),
    )
    assert done.counts == FindingCounts(confirmed=3, errors=3)
    assert wired.site.tokens == {TOKEN}
    assert await sealed(run_id) is None
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        found = await repo.findings(run_id, FindingFilter())
        weighed = [
            e.payload
            for e in await repo.evidence(
                run_id, [f.id for f in found], kinds=("relatives",)
            )
        ]
    assert sorted((f.target.key, f.error_type) for f in found) == [
        ("gene_length:NF54_SHORT", "truncated_model"),
        (f"gene_split:{SPLIT}", "split_model"),
        (f"pseudogene_call:{NF54_PIGA}+{PIGA}", "intact_gene_called_pseudogene"),
    ]
    assert _model_lengths(list(weighed)) == [200, 410]
    assert sorted((f.target.key, f.impact) for f in found) == [
        ("gene_length:NF54_SHORT", 0.5),
        (f"gene_split:{SPLIT}", 0.3),
        (f"pseudogene_call:{NF54_PIGA}+{PIGA}", 0.5),
    ]
    assert sorted(wired.evidence_reads) == ["NF54_A", "NF54_B", "NF54_SHORT", NF54_PIGA]
    stages = (await owned_run(run_id, owner)).stages.stages
    assert [(s.name, s.done == s.total, bool(s.message)) for s in stages] == [
        ("collect", True, True),
        ("screen", True, True),
        ("confirm", True, True),
        ("tie_break", True, True),
    ]


async def test_a_run_whose_job_crashed_resumes_under_the_same_lock(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.pseudogene_crashes = 1
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    with pytest.raises(RuntimeError, match="a library bug"):
        await work(jobs, queued(jobs)[0])
    stopped = await owned_run(run_id, owner)
    assert (stopped.status, stopped.stages.next_stage) == ("running", "confirm")
    assert stopped.stages.halted == "the audit job failed: RuntimeError: a library bug"
    assert (await run_view(run_id, owner.user_id)).stages.halted == (
        stopped.stages.halted
    )
    assert (queued(jobs), await sealed(run_id)) == ([], None)
    asked = list(wired.asked)

    await start_run(run_id, owner)

    assert await work_through(jobs) == 1
    assert len(wired.site.genome_reads) == 10
    assert wired.asked[len(asked) :] == [NF54_PIGA]
    resumed = await owned_run(run_id, owner)
    assert (resumed.status, resumed.stages.halted) == ("finished", None)


async def test_a_queued_job_on_a_halted_run_writes_nothing(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.set_halted(run_id, "the audit job failed: RuntimeError: x")
        await repo.record_progress(run_id, "collect", done=0, total=10, message="m")
        await session.commit()
    before = (await owned_run(run_id, owner)).stages

    assert await work_through(jobs) == 1

    assert (await owned_run(run_id, owner)).stages == before
    assert (wired.site.genome_reads, wired.site.release_reads) == ([], 0)


async def test_a_unit_a_job_stops_on_three_times_is_failed(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.pseudogene_crashes = 10
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    crashed = 0
    for _ in range(4):
        await start_run(run_id, owner)
        try:
            await work(jobs, queued(jobs)[0])
        except RuntimeError:
            crashed += 1

    assert crashed == 3
    async with async_session_factory() as session:
        (piga,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(checks=("pseudogene_call",))
        )
    assert (piga.status, piga.stopped, piga.message) == (
        "failed",
        3,
        f"{STOPPED_MESSAGE}; the audit job failed: RuntimeError: a library bug",
    )
    assert wired.asked.count(NF54_PIGA) == 3
    assert (await owned_run(run_id, owner)).status == "finished"


async def test_unreached_units_are_retried_only_when_asked(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    short_runs(monkeypatch)
    wired.split_failures.append(unanswered())
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    assert await work_through(jobs) == 1
    assert (await outcome(run_id, owner)).counts == FindingCounts(
        confirmed=2, unreached=1, errors=2
    )

    await start_run(run_id, owner)
    assert queued(jobs) == []

    await start_run(run_id, owner, retry_unreached=True)

    assert await work_through(jobs) == 1
    assert (await outcome(run_id, owner)).counts == FindingCounts(confirmed=3, errors=3)
    assert wired.asked.count(SPLIT) == 2
    assert len(wired.site.genome_reads) == 10


async def test_a_genome_read_late_leaves_the_first_sample_alone(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    short_runs(monkeypatch)
    late = "Plasmodium relative5 X"
    wired.site.failures[late].append(httpx.ConnectError("connection refused"))
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=relative_organisms(9),
        checks=("gene_length", "gene_split"),
        confirm_limit=1,
    )
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=scope)
    await start_run(run_id, owner)
    await work_through(jobs)
    assert (await outcome(run_id, owner)).unreached_genomes == (late,)
    async with async_session_factory() as session:
        before = await AuditFindingRepository(session).findings(run_id, FindingFilter())

    await start_run(run_id, owner, retry_unreached=True)
    await work_through(jobs)

    second = await outcome(run_id, owner)
    assert (second.status, second.unreached_genomes) == ("finished", ())
    assert wired.site.genome_reads.count(late) == 2
    async with async_session_factory() as session:
        after = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    assert [(f.target.key, f.sampled) for f in after] == [
        (f.target.key, f.sampled) for f in before
    ]
    assert Counter(f.target.key.split(":")[0] for f in before if f.sampled) == Counter(
        {"gene_split": 1, "gene_length": 1}
    )


async def test_a_finished_run_starts_nothing(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    await work_through(jobs)
    asked = len(wired.asked)

    done = await start_run(run_id, owner, retry_unreached=True)

    assert done.status == "finished"
    assert (len(audit_jobs(jobs)), len(wired.asked)) == (1, asked)


async def test_a_job_for_a_run_another_job_holds_reads_nothing(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)

    async with advisory_lease(audit_lock(run_id)) as held:
        assert held
        await work(jobs, queued(jobs)[0])

    assert (wired.site.genome_reads, wired.site.release_reads) == ([], 0)
    assert (await owned_run(run_id, owner)).status == "planned"


async def test_a_job_for_a_purged_run_ends_quietly(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    async with async_session_factory() as session:
        await AuditRepository(session).delete_runs(user_id=owner.user_id, site_id=None)
        await session.commit()

    assert await work_through(jobs) == 1
    assert wired.site.genome_reads == []
