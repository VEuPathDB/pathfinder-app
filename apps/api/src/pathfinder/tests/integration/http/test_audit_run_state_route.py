"""A run read from its route names its phase, the action its page may take, why it halted and the units it left unread or unreached."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI

from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.verdicts import ReviewProgress
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import NF54, seed_thread
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)

SHORT = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
LATE = SingleGeneTarget(check="gene_length", genes=("NF54_LATE",))
DEADLINE = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
NOT_READ = "not read before the run's deadline"
UNANSWERED = "plasmodb did not answer"


async def _run(owner: RunOwner) -> UUID:
    return await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(SHORT, LATE))
    )


async def _finished_with_units_left() -> tuple[RunOwner, UUID]:
    owner = await seed_thread()
    run_id = await _run(owner)
    async with async_session_factory() as session:
        findings = AuditFindingRepository(session)
        await findings.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
                NewFinding(
                    genome=NF54,
                    target=LATE,
                    sampled=True,
                    status="unread",
                    message=NOT_READ,
                ),
            ],
        )
        short = (await findings.findings(run_id, FindingFilter(keys=(SHORT.key,))))[0]
        await findings.try_finding(short.id)
        await findings.settle_finding(short.id, SettledFinding(status="confirmed"))
        await findings.try_evidence(short.id, "relatives")
        await findings.fail_evidence(
            short.id, "relatives", status="unreached", message=UNANSWERED, requests=1
        )
        repo = AuditRepository(session)
        await repo.set_deadline(run_id, DEADLINE)
        for stage in ("collect", "screen", "confirm", "tie_break"):
            await repo.finish_stage(run_id, stage)
        await repo.set_status(run_id, "finished")
        await session.commit()
    return owner, run_id


async def test_a_planned_run_is_not_started_until_it_has_a_deadline(
    app: FastAPI,
) -> None:
    owner = await seed_thread()
    run_id = await _run(owner)
    async with client_for(app, owner.user_id) as client:
        before = (await client.get(f"/api/v1/audits/{run_id}")).json()
        async with async_session_factory() as session:
            await AuditRepository(session).set_deadline(run_id, DEADLINE)
            await session.commit()
        after = (await client.get(f"/api/v1/audits/{run_id}")).json()
        listed = (await client.get("/api/v1/audits")).json()
    assert (before["run"]["phase"], before["action"], before["halt"]) == (
        "not_started",
        None,
        None,
    )
    assert before["run"]["conversationId"] == str(owner.conversation_id)
    assert (after["run"]["phase"], after["action"]) == ("queued", None)
    assert [(run["id"], run["phase"]) for run in listed] == [(str(run_id), "queued")]


async def test_a_run_halted_for_its_sign_in_offers_resume(app: FastAPI) -> None:
    owner = await seed_thread()
    run_id = await _run(owner)
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.set_deadline(run_id, DEADLINE)
        await repo.set_status(run_id, "running")
        await repo.set_halted(run_id, "sign-in needed")
        await session.commit()
    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert (run["run"]["phase"], run["action"], run["halt"]) == (
        "halted",
        "resume",
        {"kind": "sign_in", "detail": "sign-in needed"},
    )
    assert run["left"] == {"genomes": 0, "findings": 0, "evidence": 0, "total": 0}


async def test_a_finished_run_with_units_left_offers_retry(app: FastAPI) -> None:
    owner, run_id = await _finished_with_units_left()
    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert (run["run"]["phase"], run["action"], run["reviewsRunning"]) == (
        "finished",
        "retry",
        False,
    )
    assert run["left"] == {"genomes": 0, "findings": 1, "evidence": 1, "total": 2}
    assert run["evidence"] == [{"kind": "relatives", "status": "unreached", "count": 1}]


async def test_a_finished_run_whose_reviews_run_offers_no_retry(app: FastAPI) -> None:
    owner, run_id = await _finished_with_units_left()
    async with async_session_factory() as session:
        await AuditReviewRepository(session).set_review(
            run_id, ReviewProgress(status="reviewing", done=1, total=3)
        )
        await session.commit()
    async with client_for(app, owner.user_id) as client:
        reviewing = (await client.get(f"/api/v1/audits/{run_id}")).json()
        async with async_session_factory() as session:
            await AuditReviewRepository(session).set_review(
                run_id, ReviewProgress(status="synthesized", done=3, total=3)
            )
            await session.commit()
        synthesized = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert (reviewing["action"], reviewing["reviewsRunning"]) == (None, True)
    assert (synthesized["action"], synthesized["reviewsRunning"]) == ("retry", False)
