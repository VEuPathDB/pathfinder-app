from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector

from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.stages import SIGN_IN_NEEDED
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import AuditFindingRepository
from pathfinder.platform.config import get_settings
from pathfinder.services.audit.job import start_run
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import (
    SHORT_GROUP,
    TOKEN,
    Checks,
    holding,
    queued,
    registered,
    sign_in_fails_after,
    sign_in_unanswered_after,
    wire_checks,
    work,
    work_through,
)
from pathfinder.tests.integration.jobs._audit_reviews import work_reviews

GENES = [f"{SHORT_GROUP}_REL{n}" for n in range(6)]
_REFUSED_SENTENCE = "plasmodb answered 403 to the audit reads"


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


async def _run(jobs: InMemoryConnector) -> tuple[RunOwner, UUID]:
    owner = await seed_thread()
    scope = AuditScope(
        site_id="plasmodb",
        targets=tuple(
            SingleGeneTarget(check="gene_length", genes=(gene,)) for gene in GENES
        ),
    )
    run_id = await create_run(owner=owner, scope=scope)
    await start_run(run_id, owner)
    return owner, run_id


async def _messages(run_id: UUID) -> dict[str, str | None]:
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(statuses=("failed",))
        )
    return {finding.target.genes[0]: finding.message for finding in found}


async def test_a_retry_of_units_refused_under_a_holding_sign_in_terminates(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.refused_genes = {GENES[0], GENES[2], GENES[4]}
    owner, run_id = await _run(jobs)
    await work_through(jobs)
    await work_reviews(jobs)
    before = await run_view(run_id, owner.user_id)
    assert (before.run.phase, before.action, before.left.refused) == (
        "finished",
        "retry",
        3,
    )
    reviewed = await owned_run(run_id, owner)
    synthesis, review = reviewed.synthesis, reviewed.review
    assert synthesis is not None

    await start_run(run_id, owner, retry_unreached=True)
    await work_through(jobs)

    after = await run_view(run_id, owner.user_id)
    assert (
        after.run.phase,
        after.action,
        after.halt,
        after.left.total,
        after.reviews_running,
    ) == ("finished", None, None, 0, False)
    assert await _messages(run_id) == dict.fromkeys(
        (GENES[0], GENES[2], GENES[4]), _REFUSED_SENTENCE
    )
    stored = await owned_run(run_id, owner)
    assert stored.synthesis == synthesis
    assert stored.review == review
    assert stored.review is not None
    assert stored.review.status == "synthesized"
    assert queued(jobs) == []


async def test_two_units_that_always_refuse_stop_offering_a_retry_after_one_attempt(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.refused_genes = {GENES[0], GENES[1]}
    owner, run_id = await _run(jobs)
    await work_through(jobs)
    await work_reviews(jobs)
    assert (await run_view(run_id, owner.user_id)).action == "retry"

    await start_run(run_id, owner, retry_unreached=True)
    await work_through(jobs)

    after = await run_view(run_id, owner.user_id)
    assert (after.action, after.left.refused) == (None, 0)
    assert sorted(await _messages(run_id)) == [GENES[0], GENES[1]]


async def test_a_streak_under_a_holding_sign_in_fails_only_its_units(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.refused_genes = {GENES[0], GENES[1], GENES[2]}
    owner, run_id = await _run(jobs)
    await work_through(jobs)
    await work_reviews(jobs)
    view = await run_view(run_id, owner.user_id)
    assert (view.run.phase, view.halt, view.action, view.left.refused) == (
        "finished",
        None,
        None,
        0,
    )
    assert (await owned_run(run_id, owner)).stages.refusal_streak == 0
    assert await _messages(run_id) == dict.fromkeys(GENES[:3], _REFUSED_SENTENCE)


async def test_refusals_between_unanswered_reads_ask_the_sign_in_and_go_on(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.refused_genes = {GENES[0], GENES[2], GENES[4]}
    wired.unanswered_genes = [GENES[1], GENES[3]]
    owner, run_id = await _run(jobs)
    await work_through(jobs)
    await work_reviews(jobs)
    view = await run_view(run_id, owner.user_id)
    assert (view.run.phase, view.halt, view.left.refused) == ("finished", None, 0)
    assert sorted(await _messages(run_id)) == [GENES[0], GENES[2], GENES[4]]


async def test_a_streak_under_a_failed_sign_in_halts_and_a_resume_reads_all(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.forbidden = 3
    sign_in_fails_after(monkeypatch, wired, TOKEN, refusals=3)
    owner, run_id = await _run(jobs)
    await work_through(jobs)
    assert (await owned_run(run_id, owner)).stages.halted == SIGN_IN_NEEDED

    registered(monkeypatch, TOKEN)
    await start_run(run_id, owner)
    await work_through(jobs)

    view = await run_view(run_id, owner.user_id)
    assert (view.run.phase, view.halt, await _messages(run_id)) == (
        "finished",
        None,
        {},
    )


async def test_a_sign_in_check_with_no_answer_pauses_and_keeps_the_flags(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.refused_genes = {GENES[0], GENES[1], GENES[2]}
    sign_in_unanswered_after(monkeypatch, wired, TOKEN, refusals=3)
    owner, run_id = await _run(jobs)
    await work(jobs, queued(jobs)[0])

    stored = await owned_run(run_id, owner)
    assert stored.stages.halted is None
    assert stored.stages.refusal_streak == 3
    assert len(queued(jobs)) == 1
    assert (await run_view(run_id, owner.user_id)).left.refused == 3


async def test_a_retry_that_reads_something_new_runs_the_review_again(
    jobs: InMemoryConnector, wired: Checks
) -> None:
    wired.refused_genes = {GENES[0]}
    owner, run_id = await _run(jobs)
    await work_through(jobs)
    await work_reviews(jobs)
    assert (await owned_run(run_id, owner)).synthesis is not None

    wired.refused_genes = set()
    await start_run(run_id, owner, retry_unreached=True)
    running = await owned_run(run_id, owner)
    assert running.synthesis is not None
    await work_through(jobs)

    read = await owned_run(run_id, owner)
    assert read.review is not None
    assert (read.synthesis, read.review.status) == (None, "waiting")
    assert await _messages(run_id) == {}


async def test_a_sign_in_that_holds_after_a_pause_clears_the_flags(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.refused_genes = {GENES[0], GENES[1], GENES[2]}
    sign_in_unanswered_after(monkeypatch, wired, TOKEN, refusals=3)
    owner, run_id = await _run(jobs)
    await work(jobs, queued(jobs)[0])
    paused = await owned_run(run_id, owner)
    assert paused.stages.sign_in_unanswered is True

    registered(monkeypatch, TOKEN)
    await work_through(jobs)

    stored = await owned_run(run_id, owner)
    view = await run_view(run_id, owner.user_id)
    assert (
        stored.stages.refusal_streak,
        stored.stages.sign_in_unanswered,
        stored.stages.halted,
    ) == (0, False, None)
    assert (view.run.phase, view.left.refused) == ("finished", 0)


async def test_a_sign_in_that_holds_after_a_paused_retry_clears_the_flag(
    jobs: InMemoryConnector, wired: Checks, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.refused_genes = {GENES[0]}
    owner, run_id = await _run(jobs)
    await work_through(jobs)
    await work_reviews(jobs)
    assert (await run_view(run_id, owner.user_id)).left.refused == 1

    sign_in_unanswered_after(monkeypatch, wired, TOKEN, refusals=2)
    await start_run(run_id, owner, retry_unreached=True)
    await work(jobs, queued(jobs)[0])
    assert (await owned_run(run_id, owner)).stages.sign_in_unanswered is True

    registered(monkeypatch, TOKEN)
    await work_through(jobs)

    view = await run_view(run_id, owner.user_id)
    assert (view.run.phase, view.left.refused) == ("finished", 0)
