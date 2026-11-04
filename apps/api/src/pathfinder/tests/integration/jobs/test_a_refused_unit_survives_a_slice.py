from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from procrastinate.testing import InMemoryConnector

from pathfinder.domain.audit.stages import SIGN_IN_NEEDED
from pathfinder.platform.config import get_settings
from pathfinder.services.audit.job import outcome, start_run
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import (
    SCOPE,
    TOKEN,
    Checks,
    holding,
    queued,
    registered,
    sign_in_fails_after,
    split_finding,
    unanswered,
    wire_checks,
    work,
    work_through,
)
from pathfinder.tests.integration.jobs._audit_reviews import work_reviews


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


async def _first_slice(jobs: InMemoryConnector, wired: Checks) -> tuple[RunOwner, UUID]:
    wired.forbidden = 2
    wired.pseudogene_failures = [unanswered()]
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    await work(jobs, queued(jobs)[0])
    assert (await owned_run(run_id, owner)).stages.halted is None
    assert (await split_finding(run_id)).status == "failed"
    assert len(queued(jobs)) == 1
    return owner, run_id


async def test_the_third_refusal_across_a_slice_halts_as_sign_in_needed(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id = await _first_slice(jobs, wired)
    wired.forbidden = 1
    sign_in_fails_after(monkeypatch, wired, TOKEN, refusals=3)

    await work_through(jobs)

    assert (await owned_run(run_id, owner)).stages.halted == SIGN_IN_NEEDED
    assert (await split_finding(run_id)).status == "screened"


async def test_the_flagged_units_read_confirmed_after_a_resume(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id = await _first_slice(jobs, wired)
    wired.forbidden = 1
    sign_in_fails_after(monkeypatch, wired, TOKEN, refusals=3)
    await work_through(jobs)

    registered(monkeypatch, TOKEN)
    await start_run(run_id, owner)
    await work_through(jobs)

    done = await outcome(run_id, owner)
    assert (done.phase, done.counts.failed, done.counts.confirmed) == (
        "finished",
        0,
        3,
    )


async def test_a_sign_in_revoked_between_slices_reopens_the_flagged_units(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id = await _first_slice(jobs, wired)
    registered(monkeypatch)
    await work_through(jobs)
    assert (await owned_run(run_id, owner)).stages.halted == SIGN_IN_NEEDED
    assert (await split_finding(run_id)).status == "screened"

    registered(monkeypatch, TOKEN)
    await start_run(run_id, owner)
    await work_through(jobs)

    done = await outcome(run_id, owner)
    assert (done.phase, done.counts.failed, done.counts.confirmed) == (
        "finished",
        0,
        3,
    )


async def test_a_finished_run_holding_flagged_units_offers_a_retry_that_reads_them(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    owner, run_id = await _first_slice(jobs, wired)
    await work_through(jobs)
    await work_reviews(jobs)

    view = await run_view(run_id, owner.user_id)
    assert (view.run.phase, view.action, view.left.refused, view.left.total) == (
        "finished",
        "retry",
        2,
        2,
    )

    await start_run(run_id, owner, retry_unreached=True)
    await work_through(jobs)
    await work_reviews(jobs)

    done = await run_view(run_id, owner.user_id)
    assert (done.run.phase, done.action, done.left.total) == ("finished", None, 0)
    assert (await split_finding(run_id)).status == "confirmed"


async def test_an_answer_between_refusals_keeps_a_slice_from_halting(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in_fails_after(monkeypatch, wired, TOKEN, refusals=3)
    wired.forbidden = 1
    wired.answered_first = 0
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    wired.pseudogene_failures = [unanswered()]
    await start_run(run_id, owner)
    await work(jobs, queued(jobs)[0])
    stored = await owned_run(run_id, owner)
    assert stored.stages.refusal_streak == 0
    wired.forbidden = 2

    await work_through(jobs)

    assert (await owned_run(run_id, owner)).stages.halted is None


async def test_a_refusal_the_streak_counted_is_stored_for_the_next_slice(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    owner, run_id = await _first_slice(jobs, wired)
    assert (await owned_run(run_id, owner)).stages.refusal_streak == 2
