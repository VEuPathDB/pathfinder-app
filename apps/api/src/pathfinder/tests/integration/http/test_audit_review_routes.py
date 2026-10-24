"""The audit read routes carry a run's review progress, its synthesis and each finding's stored review."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.verdicts import (
    ErrorTypeSection,
    FindingReview,
    GeneModelVerdict,
    ReviewAgreement,
    ReviewProgress,
    StoredSynthesis,
    finding_cite,
)
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)

_GENOME = "Examplea alpha A"
_REVIEWED = SingleGeneTarget(check="gene_length", genes=("EXA_0001",))
_UNREVIEWED = SingleGeneTarget(check="gene_length", genes=("EXA_0002",))
_CAUSE = "The model stops before the end its relatives share."
_SUMMARY = "One synthetic gene model is truncated."


def _review(finding_id: int) -> FindingReview:
    return FindingReview(
        verdict=GeneModelVerdict(
            genes=("EXA_0001",),
            model_genome=_GENOME,
            verdict="error",
            error_type="truncated_model",
            certainty="high",
            cause=_CAUSE,
            cites=(finding_cite(finding_id),),
        ),
        already_known="not_searched",
        card_text="A truncated model of a synthetic gene.",
        second_verdict="error",
    )


def _synthesis(finding_id: int) -> StoredSynthesis:
    return StoredSynthesis(
        sections=(
            ErrorTypeSection(
                error_type="truncated_model",
                cause=_CAUSE,
                confirmed_by="The relatives of the gene are longer.",
                finding_ids=(finding_id,),
            ),
        ),
        headline=(finding_id,),
        summary=_SUMMARY,
        agreement=ReviewAgreement(sampled=1, agreed=1),
    )


async def _reviewed_run() -> tuple[RunOwner, UUID, int, int]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner,
        scope=AuditScope(site_id="plasmodb", targets=(_REVIEWED, _UNREVIEWED)),
    )
    async with async_session_factory() as session:
        findings = AuditFindingRepository(session)
        await findings.add_findings(
            run_id,
            [
                NewFinding(genome=_GENOME, target=t, sampled=True, status="screened")
                for t in (_REVIEWED, _UNREVIEWED)
            ],
        )
        reviewed, unreviewed = await findings.findings(run_id, FindingFilter())
        for finding_id in (reviewed.id, unreviewed.id):
            await findings.try_finding(finding_id)
            await findings.settle_finding(
                finding_id,
                SettledFinding(
                    status="confirmed", error_type="truncated_model", certainty="high"
                ),
            )
        reviews = AuditReviewRepository(session)
        await reviews.add_review(
            run_id=run_id,
            finding_id=reviewed.id,
            review=_review(reviewed.id),
            model_id="test:reviewer",
        )
        await reviews.set_review(
            run_id, ReviewProgress(status="synthesized", done=1, total=2)
        )
        await reviews.set_synthesis(run_id, _synthesis(reviewed.id))
        await session.commit()
    return owner, run_id, reviewed.id, unreviewed.id


@contextmanager
def _statements(engine: AsyncEngine) -> Iterator[list[str]]:
    seen: list[str] = []

    def _record(*args: object) -> None:
        seen.append(str(args[2]))

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)


async def test_a_run_reads_with_its_review_and_synthesis(app: FastAPI) -> None:
    owner, run_id, reviewed_id, _ = await _reviewed_run()

    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()

    assert (run["review"], run["reviewed"]) == (
        {"status": "synthesized", "done": 1, "total": 2, "message": ""},
        1,
    )
    assert run["synthesis"] == {
        "sections": [
            {
                "errorType": "truncated_model",
                "cause": _CAUSE,
                "confirmedBy": "The relatives of the gene are longer.",
                "findingIds": [reviewed_id],
            }
        ],
        "headline": [reviewed_id],
        "summary": _SUMMARY,
        "agreement": {"sampled": 1, "agreed": 1, "share": 1.0},
    }


async def test_a_run_with_no_review_reads_with_none(app: FastAPI) -> None:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(_REVIEWED,))
    )

    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()

    assert (run["review"], run["synthesis"], run["reviewed"]) == (None, None, 0)


async def test_a_finding_reads_with_its_stored_review(app: FastAPI) -> None:
    owner, run_id, reviewed_id, unreviewed_id = await _reviewed_run()
    url = f"/api/v1/audits/{run_id}/findings"

    async with client_for(app, owner.user_id) as client:
        reviewed = (await client.get(f"{url}/{reviewed_id}")).json()
        unreviewed = (await client.get(f"{url}/{unreviewed_id}")).json()

    review = reviewed["review"]
    assert (
        review["verdict"]["verdict"],
        review["verdict"]["errorType"],
        review["verdict"]["cites"],
        review["alreadyKnown"],
        review["secondVerdict"],
    ) == (
        "error",
        "truncated_model",
        [f"finding:{reviewed_id}"],
        "not_searched",
        "error",
    )
    assert (reviewed["finding"]["reviewed"], unreviewed["finding"]["reviewed"]) == (
        True,
        False,
    )
    assert unreviewed["review"] is None


async def test_findings_read_their_reviews_in_one_query(
    app: FastAPI, db_engine: AsyncEngine
) -> None:
    owner, run_id, reviewed_id, unreviewed_id = await _reviewed_run()

    with _statements(db_engine) as seen:
        async with client_for(app, owner.user_id) as client:
            page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()

    assert [(f["id"], f["reviewed"]) for f in page["findings"]] == [
        (reviewed_id, True),
        (unreviewed_id, False),
    ]
    assert [f["reviewLine"] is None for f in page["findings"]] == [False, True]
    (reading_verdicts,) = [s for s in seen if "audit_verdicts" in s]
    assert "FROM audit_findings LEFT OUTER JOIN audit_verdicts" in reading_verdicts
