"""The verdict rows and a run's review state: written, read by owner, ordered by impact."""

from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.platform.context import application_id_ctx
from assistant_core.platform.db import async_session_factory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pathfinder.domain.audit.findings import Certainty, ErrorType
from pathfinder.domain.audit.rates import Weighing
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.verdicts import (
    ErrorTypeSection,
    FindingReview,
    GeneModelVerdict,
    ReviewAgreement,
    ReviewProgress,
    Synthesis,
    finding_cite,
)
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.persistence.repositories.audit_tallies import AuditTallyRepository
from pathfinder.persistence.repositories.audit_weighings import AuditWeighingRepository
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import seed_thread

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_GENOME = "Examplea alpha A"
_MODEL = "test:reviewer"
_CERTAINTIES = {0.3: "medium", 1.0: "high", 0.075: "low"}


def _verdict(gene: str, finding_id: int) -> GeneModelVerdict:
    return GeneModelVerdict(
        genes=(gene,),
        model_genome=_GENOME,
        verdict="error",
        error_type="truncated_model",
        certainty="high",
        cause="The model stops before the end its relatives share.",
        cites=(finding_cite(finding_id),),
    )


def _review(gene: str, finding_id: int) -> FindingReview:
    return FindingReview(
        verdict=_verdict(gene, finding_id),
        already_known="not_searched",
        card_text="A truncated model of a synthetic gene.",
    )


def _weighing(impact: float) -> Weighing:
    return Weighing.model_validate(
        {
            "certainty": _CERTAINTIES[impact],
            "importance": {
                "genes": ["EXA_0001"],
                "source": "cited" if impact == 1.0 else "uncited",
            },
            "use": {
                "genome": _GENOME,
                "source": "other_strain" if impact == 0.075 else "reference_strain",
                "reference": impact != 0.075,
            },
        }
    )


async def _run_with_findings(
    impacts: list[float],
) -> tuple[RunOwner, UUID, dict[float, int]]:
    owner = await seed_thread("toxodb")
    targets = [
        SingleGeneTarget(check="gene_length", genes=(f"EXA_{k + 1:04d}",))
        for k in range(len(impacts))
    ]
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="toxodb", targets=tuple(targets))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=_GENOME, target=t, sampled=True, status="screened")
                for t in targets
            ],
        )
        ids = [f.id for f in await repo.findings(run_id, FindingFilter())]
        for finding_id, impact in zip(ids, impacts, strict=True):
            weighing = _weighing(impact)
            await repo.try_finding(finding_id)
            await repo.settle_finding(
                finding_id,
                SettledFinding(
                    status="confirmed",
                    genome=_GENOME,
                    error_type="truncated_model",
                    certainty=weighing.certainty,
                ),
            )
            await AuditWeighingRepository(session).set_impact(finding_id, weighing)
        await session.commit()
    return owner, run_id, dict(zip(impacts, ids, strict=True))


async def _add_review(run_id: UUID, finding_id: int) -> int:
    async with async_session_factory() as session:
        added = await AuditReviewRepository(session).add_review(
            run_id=run_id,
            finding_id=finding_id,
            review=_review("EXA_0001", finding_id),
            model_id=_MODEL,
        )
        await session.commit()
    return added


async def test_unreviewed_findings_come_by_impact_and_a_review_is_stored_once() -> None:
    owner, run_id, ids = await _run_with_findings([0.3, 1.0, 0.075])
    async with async_session_factory() as session:
        first = await AuditReviewRepository(session).unreviewed(run_id, 2)
    assert first == [ids[1.0], ids[0.3]]

    await _add_review(run_id, ids[1.0])

    async with async_session_factory() as session:
        repo = AuditReviewRepository(session)
        after = await repo.unreviewed(run_id, 2)
        reviewed = await repo.reviewed_count(run_id)
        (stored,) = await repo.of_run(run_id)
        owned = await repo.of_conversation(owner.conversation_id, owner.user_id)
    assert after == [ids[0.3], ids[0.075]]
    assert reviewed == 1
    assert (stored.finding_id, stored.origin, stored.model_id) == (
        ids[1.0],
        "review",
        _MODEL,
    )
    assert owned == [stored]
    assert stored.site_id == "toxodb"
    assert stored.review == _review("EXA_0001", ids[1.0])
    assert stored.verdict == _verdict("EXA_0001", ids[1.0])

    with pytest.raises(IntegrityError):
        await _add_review(run_id, ids[1.0])


async def test_a_chat_verdict_is_read_by_its_owner_alone() -> None:
    owner = await seed_thread("toxodb")
    other = await seed_thread("toxodb")
    verdict = _verdict("EXA_0002", 1).model_copy(
        update={"cites": ("audit_gene_length:EXA_0002",)}
    )
    async with async_session_factory() as session:
        await AuditReviewRepository(session).add_verdict(
            user_id=owner.user_id,
            conversation_id=owner.conversation_id,
            site_id="toxodb",
            origin="auditor",
            verdict=verdict,
            model_id=_MODEL,
        )
        await session.commit()

    async with async_session_factory() as session:
        repo = AuditReviewRepository(session)
        mine = await repo.of_conversation(owner.conversation_id, owner.user_id)
        theirs = await repo.of_conversation(owner.conversation_id, other.user_id)
        nulls = await session.scalar(
            text("SELECT count(*) FROM audit_verdicts WHERE review IS NULL")
        )
    token = application_id_ctx.set("another-application")
    try:
        async with async_session_factory() as session:
            elsewhere = await AuditReviewRepository(session).of_conversation(
                owner.conversation_id, owner.user_id
            )
    finally:
        application_id_ctx.reset(token)
    assert [(v.origin, v.verdict, v.review, v.run_id) for v in mine] == [
        ("auditor", verdict, None, None)
    ]
    assert theirs == []
    assert elsewhere == []
    assert nulls == 1


async def test_a_conversations_verdicts_come_newest_first() -> None:
    owner = await seed_thread("toxodb")
    for gene in ("EXA_0004", "EXA_0005"):
        async with async_session_factory() as session:
            await AuditReviewRepository(session).add_verdict(
                user_id=owner.user_id,
                conversation_id=owner.conversation_id,
                site_id="toxodb",
                origin="lead",
                verdict=_verdict(gene, 1).model_copy(
                    update={"cites": (f"audit_gene_length:{gene}",)}
                ),
                model_id=_MODEL,
            )
            await session.commit()

    async with async_session_factory() as session:
        found = await AuditReviewRepository(session).of_conversation(
            owner.conversation_id, owner.user_id
        )
    assert [v.verdict.genes for v in found] == [("EXA_0005",), ("EXA_0004",)]
    assert found[0].created_at > found[1].created_at


async def test_pending_reviews_are_finished_runs_still_reviewing() -> None:
    _, reviewing, _ = await _run_with_findings([1.0])
    _, synthesized, _ = await _run_with_findings([0.3])
    _, halted, _ = await _run_with_findings([0.075])
    _, unfinished, _ = await _run_with_findings([1.0])
    synthesis = Synthesis(
        sections=(
            ErrorTypeSection(
                error_type="truncated_model",
                cause="Models stop early.",
                confirmed_by="The relatives of each gene.",
                finding_ids=(1,),
            ),
        ),
        headline=(1,),
        summary="One synthetic error type.",
        agreement=ReviewAgreement(sampled=0, agreed=0),
    )
    async with async_session_factory() as session:
        runs, reviews = AuditRepository(session), AuditReviewRepository(session)
        for run_id in (reviewing, synthesized, halted):
            await runs.set_status(run_id, "finished")
        await runs.set_halted(halted, "the site refused the sign-in")
        await reviews.set_review(reviewing, ReviewProgress(status="reviewing", done=1))
        await reviews.set_review(synthesized, ReviewProgress(status="synthesized"))
        await reviews.set_synthesis(synthesized, synthesis)
        for run_id in (halted, unfinished):
            await reviews.set_review(run_id, ReviewProgress(status="waiting"))
        await session.commit()

    async with async_session_factory() as session:
        pending = await AuditReviewRepository(session).pending_reviews()
        stored = await AuditRepository(session).run(
            synthesized, user_id=await _owner_of(synthesized)
        )
        fresh = await AuditRepository(session).run(
            unfinished, user_id=await _owner_of(unfinished)
        )
    assert pending == [reviewing]
    assert stored is not None
    assert (stored.review, stored.synthesis) == (
        ReviewProgress(status="synthesized"),
        synthesis,
    )
    assert fresh is not None
    assert (fresh.review, fresh.synthesis) == (ReviewProgress(status="waiting"), None)


async def _owner_of(run_id: UUID) -> UUID:
    async with async_session_factory() as session:
        stored = await AuditRepository(session).stored_run(run_id)
    assert stored is not None
    return stored.user_id


async def test_a_purge_deletes_one_sites_verdicts_or_every_sites() -> None:
    owner = await seed_thread("toxodb")
    verdict = _verdict("EXA_0003", 1).model_copy(
        update={"cites": ("audit_gene_length:EXA_0003",)}
    )
    async with async_session_factory() as session:
        repo = AuditReviewRepository(session)
        for site_id in ("toxodb", "plasmodb"):
            await repo.add_verdict(
                user_id=owner.user_id,
                conversation_id=owner.conversation_id,
                site_id=site_id,
                origin="lead",
                verdict=verdict,
                model_id=_MODEL,
            )
        await session.commit()

    async with async_session_factory() as session:
        repo = AuditReviewRepository(session)
        one = await repo.delete_for_user(user_id=owner.user_id, site_id="plasmodb")
        rest = await repo.of_conversation(owner.conversation_id, owner.user_id)
        every = await repo.delete_for_user(user_id=owner.user_id, site_id=None)
        await session.commit()
    assert (one, [v.site_id for v in rest], every) == (1, ["toxodb"], 1)
    with pytest.raises(ValueError, match="names a site"):
        async with async_session_factory() as session:
            await AuditReviewRepository(session).delete_for_user(
                user_id=owner.user_id, site_id=""
            )


async def test_a_finding_reads_with_its_review_in_one_join() -> None:
    _, run_id, ids = await _run_with_findings([0.3, 1.0, 0.075])
    await _add_review(run_id, ids[1.0])

    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        found = await repo.findings(run_id, FindingFilter(), by_impact=True)
        one = await repo.finding(run_id, ids[1.0])
        other = await repo.finding(run_id, ids[0.3])

    assert [(f.id, f.review, f.reviewed) for f in found] == [
        (ids[1.0], _review("EXA_0001", ids[1.0]), True),
        (ids[0.3], None, False),
        (ids[0.075], None, False),
    ]
    assert one is not None
    assert other is not None
    assert (one.review, other.review) == (_review("EXA_0001", ids[1.0]), None)


async def test_the_error_type_tally_counts_named_findings_by_genome_and_certainty() -> (
    None
):
    _, run_id, _ = await _run_with_findings([0.3, 1.0, 0.075])
    await _run_with_findings([1.0])
    unnamed = SingleGeneTarget(check="gene_length", genes=("EXA_0009",))
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(
                    genome=_GENOME, target=unnamed, sampled=True, status="screened"
                )
            ],
        )
        (finding,) = await repo.findings(run_id, FindingFilter(keys=(unnamed.key,)))
        await repo.try_finding(finding.id)
        await repo.settle_finding(finding.id, SettledFinding(status="confirmed"))
        await session.commit()

    async with async_session_factory() as session:
        tally = await AuditTallyRepository(session).error_type_tally(run_id)

    assert tally == [
        ("truncated_model", _GENOME, "high", 1),
        ("truncated_model", _GENOME, "low", 1),
        ("truncated_model", _GENOME, "medium", 1),
    ]


async def _named_findings(
    named: list[tuple[ErrorType, Certainty]],
) -> tuple[UUID, list[int]]:
    owner = await seed_thread("toxodb")
    targets = [
        SingleGeneTarget(check="gene_length", genes=(f"EXA_{k + 1:04d}",))
        for k in range(len(named))
    ]
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="toxodb", targets=tuple(targets))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=_GENOME, target=t, sampled=True, status="screened")
                for t in targets
            ],
        )
        ids = [f.id for f in await repo.findings(run_id, FindingFilter())]
        for finding_id, (error_type, certainty) in zip(ids, named, strict=True):
            await repo.try_finding(finding_id)
            await repo.settle_finding(
                finding_id,
                SettledFinding(
                    status="confirmed",
                    genome=_GENOME,
                    error_type=error_type,
                    certainty=certainty,
                ),
            )
        await session.commit()
    return run_id, ids


async def _review_as(run_id: UUID, finding_id: int, verdict: GeneModelVerdict) -> None:
    review = _review("EXA_0001", finding_id).model_copy(update={"verdict": verdict})
    async with async_session_factory() as session:
        await AuditReviewRepository(session).add_review(
            run_id=run_id, finding_id=finding_id, review=review, model_id=_MODEL
        )
        await session.commit()


async def test_a_reviewed_type_supersedes_the_stored_type_in_the_tally() -> None:
    run_id, (first, _) = await _named_findings(
        [("truncated_model", "low"), ("split_model", "low")]
    )
    split = _verdict("EXA_0001", first).model_copy(
        update={"error_type": "split_model", "certainty": "high"}
    )
    await _review_as(run_id, first, split)

    async with async_session_factory() as session:
        tally = await AuditTallyRepository(session).error_type_tally(run_id)

    assert tally == [
        ("split_model", _GENOME, "high", 1),
        ("split_model", _GENOME, "low", 1),
    ]


async def test_a_rejecting_review_keeps_the_stored_type_in_the_tally() -> None:
    run_id, (finding_id,) = await _named_findings([("truncated_model", "medium")])
    rejected = _verdict("EXA_0001", finding_id).model_copy(
        update={"verdict": "no_error", "error_type": None, "certainty": None}
    )
    await _review_as(run_id, finding_id, rejected)

    async with async_session_factory() as session:
        tally = await AuditTallyRepository(session).error_type_tally(run_id)

    assert tally == [("truncated_model", _GENOME, "medium", 1)]
