"""An audit job waits for a site off the worker, stays inside its deadline, and runs only on its owner's kept sign-in."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from fastmcp.exceptions import ToolError
from procrastinate.testing import InMemoryConnector
from veupathdb.errors import WDKError, WDKLoginRequiredError

from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.audit.job import outcome, start_run
from pathfinder.services.audit.queue import audit_lock
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.services.audit.sign_in import AuditsDisabledError
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import (
    EXPIRED_TOKEN,
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
    split_finding,
    unanswered,
    wire_checks,
    work,
    work_through,
)
from pathfinder.tests.integration.jobs._audit_reviews import work_reviews

SIGN_IN_NEEDED = "sign-in needed"
_TOLERANCE = timedelta(seconds=5)
_LATE = "Plasmodium relative5 X"


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


def _refused(status: int) -> ToolError:
    error = ToolError("plasmodb refused the audit reads")
    error.__cause__ = WDKError(
        f"GET /record-types -> HTTP {status}: expired", status=status
    )
    return error


async def test_a_wait_for_a_site_ends_the_job_and_schedules_its_continuation(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.split_failures.append(unanswered())
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    (first,) = queued(jobs)
    paused_at = datetime.now(UTC)

    await work(jobs, first)

    (later,) = queued(jobs)
    assert (later["lock"], later["queueing_lock"]) == (audit_lock(run_id),) * 2
    assert later["args"]["payload"] == {**first["args"]["payload"], "pause": 60.0}
    assert abs(later["scheduled_at"] - (paused_at + timedelta(seconds=30))) < _TOLERANCE
    paused = await owned_run(run_id, owner)
    assert (paused.status, paused.stages.unfinished) == (
        "running",
        ("confirm", "tie_break"),
    )
    assert paused.stages.stages[2].message == (
        "waiting 30 s for plasmodb, 1 finding unanswered"
    )
    wired.site.tokens.clear()

    await work(jobs, later)

    done = await outcome(run_id, owner)
    assert (done.phase, done.counts.confirmed, done.counts.errors) == (
        "finished",
        3,
        3,
    )
    assert wired.asked.count(SPLIT) == 2
    assert wired.site.tokens == {TOKEN}


async def test_a_finished_stage_starts_the_next_one_at_the_first_pause(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.site.failures[_LATE].append(httpx.ConnectError("connection refused"))
    wired.split_failures.append(unanswered())
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    await work(jobs, queued(jobs)[0])
    (after_collect,) = queued(jobs)
    assert after_collect["args"]["payload"]["pause"] == 60.0
    paused_at = datetime.now(UTC)

    await work(jobs, after_collect)

    (in_confirm,) = queued(jobs)
    assert in_confirm["args"]["payload"]["pause"] == 60.0
    assert (
        abs(in_confirm["scheduled_at"] - (paused_at + timedelta(seconds=30)))
        < _TOLERANCE
    )
    assert (await owned_run(run_id, owner)).stages.next_stage == "confirm"


async def test_a_continuation_picked_up_after_the_deadline_reads_nothing(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.split_failures.append(unanswered())
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    await work(jobs, queued(jobs)[0])
    (later,) = queued(jobs)
    passed = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    later["args"]["payload"]["deadline"] = passed

    await work(jobs, later)

    assert wired.asked.count(SPLIT) == 1
    assert queued(jobs) == []
    done = await outcome(run_id, owner)
    assert (done.phase, done.counts.unreached) == ("finished", 1)
    split = await split_finding(run_id)
    assert (split.attempts, split.message) == (1, str(unanswered()))


@pytest.mark.parametrize("token", [None, "token-guest"])
async def test_a_start_without_a_registered_sign_in_is_refused_before_any_request(
    jobs: InMemoryConnector, wired: Checks, token: str | None
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)

    with holding(token), pytest.raises(WDKLoginRequiredError):
        await start_run(run_id, owner)

    refused = await owned_run(run_id, owner)
    assert (refused.status, refused.deadline_at, refused.stages.halted) == (
        "planned",
        None,
        SIGN_IN_NEEDED,
    )
    assert (audit_jobs(jobs), await sealed(run_id)) == ([], None)
    assert (wired.site.genome_reads, wired.site.release_reads, wired.asked) == (
        [],
        0,
        [],
    )


async def test_a_refused_retry_leaves_a_finished_run_finished(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    short_runs(monkeypatch)
    wired.split_failures.append(unanswered())
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    await work_through(jobs)
    await work_reviews(jobs)

    with holding(None), pytest.raises(WDKLoginRequiredError):
        await start_run(run_id, owner, retry_unreached=True)

    assert (await owned_run(run_id, owner)).status == "finished"
    assert (await split_finding(run_id)).status == "unreached"


async def test_a_forbidden_read_on_a_valid_sign_in_fails_only_its_unit(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.split_failures.append(_refused(403))
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)

    await work_through(jobs)

    done = await outcome(run_id, owner)
    assert (done.phase, done.halted, done.counts.failed, done.counts.confirmed) == (
        "finished",
        None,
        1,
        2,
    )
    split = await split_finding(run_id)
    assert (split.status, split.stopped, split.message) == (
        "failed",
        0,
        str(_refused(403)),
    )


@pytest.mark.parametrize(("status", "kept"), [(401, TOKEN), (403, EXPIRED_TOKEN)])
async def test_a_refused_sign_in_halts_the_run_and_a_new_one_resumes_it(
    jobs: InMemoryConnector,
    wired: Checks,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    kept: str,
) -> None:
    registered(monkeypatch, TOKEN, EXPIRED_TOKEN)
    wired.split_failures.append(_refused(status))
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(kept):
        await start_run(run_id, owner)

    await work_through(jobs)

    halted = await owned_run(run_id, owner)
    assert (halted.status, halted.stages.unfinished, halted.stages.halted) == (
        "running",
        ("confirm", "tie_break"),
        SIGN_IN_NEEDED,
    )
    confirm_stage = halted.stages.stages[2]
    assert confirm_stage.message == SIGN_IN_NEEDED
    split = await split_finding(run_id)
    assert (split.status, split.attempts, split.stopped, split.message) == (
        "screened",
        1,
        0,
        None,
    )
    assert (queued(jobs), await sealed(run_id)) == ([], None)

    with holding(TOKEN):
        await start_run(run_id, owner)
    await work_through(jobs)

    done = await outcome(run_id, owner)
    assert (done.phase, done.halted, done.counts.confirmed) == ("finished", None, 3)
    split = await split_finding(run_id)
    assert (split.status, split.attempts, split.stopped) == ("confirmed", 2, 0)
    assert len(wired.site.genome_reads) == 10


async def test_a_continuation_whose_kept_sign_in_lapsed_halts_before_a_read(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.split_failures.append(unanswered())
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)
    await work(jobs, queued(jobs)[0])
    registered(monkeypatch)

    await work(jobs, queued(jobs)[0])

    halted = await owned_run(run_id, owner)
    assert (halted.stages.halted, halted.stages.next_stage) == (
        SIGN_IN_NEEDED,
        "confirm",
    )
    assert wired.asked.count(SPLIT) == 1
    assert (queued(jobs), await sealed(run_id)) == ([], None)


async def test_a_release_read_refused_for_sign_in_halts_before_any_genome(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.site.release_failures.append(WDKError("GET / -> HTTP 401", status=401))
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)

    await work_through(jobs)

    halted = await owned_run(run_id, owner)
    assert (halted.stages.halted, halted.stages.next_stage) == (
        SIGN_IN_NEEDED,
        "collect",
    )
    assert (wired.site.genome_reads, queued(jobs)) == ([], [])


async def test_a_deployment_that_cannot_keep_a_sign_in_starts_no_audit(
    db_cleaner: None,
    patch_app_db_engine: None,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    wired: Checks,
) -> None:
    del db_cleaner, patch_app_db_engine, wired
    registered(monkeypatch, TOKEN)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)

    with holding(TOKEN), pytest.raises(AuditsDisabledError) as refused:
        await start_run(run_id, owner)

    assert (refused.value.code, refused.value.status, refused.value.title) == (
        ErrorCode.AUDITS_DISABLED,
        403,
        "Audits are off",
    )
    assert audit_jobs(in_memory_jobs) == []
    assert await sealed(run_id) is None
    untouched = await owned_run(run_id, owner)
    assert (untouched.deadline_at, untouched.stages.halted) == (None, None)


async def test_three_forbidden_units_in_a_row_halt_as_a_revoked_sign_in(
    jobs: InMemoryConnector, wired: Checks
) -> None:
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
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(sampled=True)
        )
    assert (
        sorted((f.status, f.attempts, f.stopped, f.message) for f in found)
        == [("screened", 1, 0, None)] * 3
    )
    assert (queued(jobs), await sealed(run_id)) == ([], None)

    with holding(TOKEN):
        await start_run(run_id, owner)
    await work_through(jobs)

    done = await outcome(run_id, owner)
    assert (done.phase, done.halted, done.counts.confirmed) == ("finished", None, 3)


async def test_two_forbidden_units_then_an_answer_fail_only_those_two(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.forbidden = 2
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    with holding(TOKEN):
        await start_run(run_id, owner)

    await work_through(jobs)

    done = await outcome(run_id, owner)
    assert (done.phase, done.halted, done.counts.failed, done.counts.confirmed) == (
        "finished",
        None,
        2,
        1,
    )
