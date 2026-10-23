"""Stored audit runs the read routes are tested against."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.db import async_session_factory

from pathfinder.domain.audit.confirmations import (
    IntronConfirmation,
    PseudogeneConfirmation,
)
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget, SingleGeneTarget
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    P3D7,
    PIGA,
    PIGA_INTACT,
    seed_thread,
)
from pathfinder.tests._support.audit_introns import INTRON_GENE, intron_audit

PAIR = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
SHORT = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
INTRON = SingleGeneTarget(check="intron_support", genes=(INTRON_GENE,))
UNREADABLE = "the gene record of NF54_SHORT is unreadable"
UNANSWERED = "plasmodb did not answer"


async def stored_pair_run() -> tuple[RunOwner, UUID, int]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(PAIR, SHORT))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=PAIR, sampled=True, status="screened"),
                NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
            ],
        )
        pair = (
            await repo.findings(run_id, FindingFilter(checks=("pseudogene_call",)))
        )[0]
        await repo.try_finding(pair.id)
        await repo.settle_finding(
            pair.id,
            SettledFinding(
                status="confirmed",
                error_type="intact_gene_called_pseudogene",
                certainty="high",
                requests=6,
            ),
        )
        short = (await repo.findings(run_id, FindingFilter(checks=("gene_length",))))[0]
        await repo.try_finding(short.id)
        await repo.settle_finding(
            short.id, SettledFinding(status="failed", message=UNREADABLE)
        )
        await repo.try_evidence(pair.id, "confirmation")
        await repo.save_evidence(
            pair.id,
            ConfirmationEvidence(
                confirmation=PseudogeneConfirmation(result=PIGA_INTACT)
            ),
            requests=2,
        )
        await repo.try_evidence(pair.id, "relatives")
        await repo.fail_evidence(
            pair.id, "relatives", status="unreached", message=UNANSWERED, requests=1
        )
        await session.commit()
    return owner, run_id, pair.id


async def screened_genome_run() -> tuple[RunOwner, UUID]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner,
        scope=AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            comparison=(P3D7,),
            checks=("gene_length",),
        ),
    )
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(
            run_id,
            [
                NewFinding(
                    genome=NF54,
                    target=SingleGeneTarget(check="gene_length", genes=(gene,)),
                    sampled=True,
                    status="screened",
                )
                for gene in ("NF54_SHORT", "NF54_TYPICAL")
            ],
        )
        await session.commit()
    return owner, run_id


async def stored_intron_run() -> tuple[RunOwner, UUID, int]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(INTRON,))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [NewFinding(genome=NF54, target=INTRON, sampled=True, status="screened")],
        )
        (intron,) = await repo.findings(run_id, FindingFilter())
        await repo.try_finding(intron.id)
        await repo.settle_finding(
            intron.id,
            SettledFinding(
                status="confirmed", error_type="missing_exon", certainty="high"
            ),
        )
        await repo.try_evidence(intron.id, "confirmation")
        await repo.save_evidence(
            intron.id,
            ConfirmationEvidence(
                confirmation=IntronConfirmation(
                    result=intron_audit("UNSUPPORTED_MISSING_EXON")
                )
            ),
            requests=1,
        )
        await session.commit()
    return owner, run_id, intron.id
