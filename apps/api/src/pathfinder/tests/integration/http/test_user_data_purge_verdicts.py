"""A purge deletes the judgements made about the user's genes, one site's or every site's."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.verdicts import (
    FindingReview,
    GeneModelVerdict,
    VerdictOrigin,
    finding_cite,
)
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests.integration.http._user_data_purge import (
    OTHER_SITE,
    SITE,
    add_conv,
    api_client,
    db_session,
    seed_user,
)

__all__ = ["api_client", "db_session", "seed_user"]

_VERDICT = GeneModelVerdict(
    genes=("EXA_0001",),
    model_genome="Examplea alpha A",
    verdict="no_error",
    cause="Every annotated intron has reads across it.",
    cites=("audit_intron_support:EXA_0001",),
)


async def _judged(
    db_session: AsyncSession, user_id: UUID, site_id: str, origin: VerdictOrigin
) -> UUID:
    conversation_id = await add_conv(
        db_session, user_id, site_id=site_id, wdk_strategy_id=None, created_here=False
    )
    await AuditReviewRepository(db_session).add_verdict(
        user_id=user_id,
        conversation_id=conversation_id,
        site_id=site_id,
        origin=origin,
        verdict=_VERDICT,
        model_id="test:auditor",
    )
    await db_session.commit()
    return conversation_id


async def test_a_site_purge_deletes_that_sites_verdicts_and_no_one_elses(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    gone = await _judged(db_session, seed_user.id, SITE, "auditor")
    kept = await _judged(db_session, seed_user.id, OTHER_SITE, "lead")
    stranger = User(id=uuid4())
    db_session.add(stranger)
    await db_session.commit()
    theirs = await _judged(db_session, stranger.id, SITE, "verification")

    resp = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": SITE}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["auditVerdicts"] == 1
    async with session_maker() as verify:
        repo = AuditReviewRepository(verify)
        left = [
            [v.origin for v in await repo.of_conversation(conversation_id, user_id)]
            for conversation_id, user_id in (
                (gone, seed_user.id),
                (kept, seed_user.id),
                (theirs, stranger.id),
            )
        ]
    assert left == [[], ["lead"], ["verification"]]


async def test_clearing_all_data_deletes_every_sites_verdicts(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
) -> None:
    await _judged(db_session, seed_user.id, SITE, "auditor")
    await _judged(db_session, seed_user.id, OTHER_SITE, "lead")

    resp = await api_client.request("DELETE", "/api/v1/user/data")

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["auditVerdicts"] == 2


async def _reviewed_run(db_session: AsyncSession, user_id: UUID) -> None:
    conversation_id = await add_conv(
        db_session, user_id, site_id=SITE, wdk_strategy_id=None, created_here=False
    )
    target = SingleGeneTarget(check="gene_length", genes=("EXA_0002",))
    run_id = await create_run(
        owner=RunOwner(user_id=user_id, conversation_id=conversation_id),
        scope=AuditScope(site_id=SITE, targets=(target,)),
    )
    findings = AuditFindingRepository(db_session)
    await findings.add_findings(
        run_id,
        [
            NewFinding(
                genome="Examplea alpha A",
                target=target,
                sampled=True,
                status="screened",
            )
        ],
    )
    (finding,) = await findings.findings(run_id, FindingFilter())
    await findings.try_finding(finding.id)
    await findings.settle_finding(
        finding.id,
        SettledFinding(
            status="confirmed",
            genome="Examplea alpha A",
            error_type="truncated_model",
            certainty="high",
        ),
    )
    await AuditReviewRepository(db_session).add_review(
        run_id=run_id,
        finding_id=finding.id,
        review=FindingReview(
            verdict=GeneModelVerdict(
                genes=("EXA_0002",),
                model_genome="Examplea alpha A",
                verdict="error",
                error_type="truncated_model",
                certainty="high",
                cause="The model stops before the end its relatives share.",
                cites=(finding_cite(finding.id),),
            ),
            already_known="not_searched",
            card_text="A truncated model of a synthetic gene.",
        ),
        model_id="test:reviewer",
    )
    await db_session.commit()


async def test_a_purge_counts_a_runs_reviews_among_the_verdicts_it_deletes(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
) -> None:
    await _reviewed_run(db_session, seed_user.id)
    await _judged(db_session, seed_user.id, SITE, "auditor")

    resp = await api_client.request("DELETE", "/api/v1/user/data")

    assert resp.status_code == 200, resp.text
    deleted = resp.json()["deleted"]
    assert (deleted["auditVerdicts"], deleted["auditRuns"]) == (2, 1)
