"""Stored audit runs the read routes are tested against."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import delete
from veupathdb_mcp.audit import GeneId

from pathfinder.domain.audit.confirmations import (
    IntronConfirmation,
    PseudogeneConfirmation,
)
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import (
    AuditScope,
    GenePairTarget,
    GeneTarget,
    SingleGeneTarget,
)
from pathfinder.domain.audit.stages import SIGN_IN_NEEDED
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
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
from pathfinder.tests.integration.jobs._audit_jobs import SCOPE

PAIR = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
PIGA_ALIAS = "PF10_0115"
ALIASED_PAIR = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA_ALIAS))
SHORT = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
INTRON = SingleGeneTarget(check="intron_support", genes=(INTRON_GENE,))
TARGET = SingleGeneTarget(check="gene_length", genes=("NF54_TARGET",))
SPLIT = GenePairTarget(check="gene_split", genes=("NF54_A", "NF54_B"))
UNREADABLE = "the gene record of NF54_SHORT is unreadable"
UNANSWERED = "plasmodb did not answer"
DEADLINE = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
NOT_READ = "not read before the run's deadline"


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


async def mixed_run() -> tuple[RunOwner, UUID, dict[str, int]]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner,
        scope=AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            comparison=(P3D7,),
            checks=("gene_length", "gene_split"),
            targets=(TARGET,),
        ),
    )
    settled: dict[str, tuple[GeneTarget, SettledFinding]] = {
        "short": (
            SHORT,
            SettledFinding(
                status="confirmed", error_type="truncated_model", certainty="high"
            ),
        ),
        "split": (
            SPLIT,
            SettledFinding(
                status="confirmed", error_type="split_model", certainty="medium"
            ),
        ),
        "target": (TARGET, SettledFinding(status="confirmed")),
    }
    ids: dict[str, int] = {}
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=target, sampled=True, status="screened")
                for target, _ in settled.values()
            ],
        )
        stored = {
            f.target.key: f.id for f in await repo.findings(run_id, FindingFilter())
        }
        for name, (target, settlement) in settled.items():
            ids[name] = stored[target.key]
            await repo.try_finding(ids[name])
            await repo.settle_finding(ids[name], settlement)
        await session.commit()
    return owner, run_id, ids


async def aliased_pair_run() -> tuple[RunOwner, UUID, int]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(ALIASED_PAIR,))
    )
    resolved = PIGA_INTACT.model_copy(
        update={
            "gene_ids": [
                GeneId(given=NF54_PIGA, resolved=NF54_PIGA),
                GeneId(given=PIGA_ALIAS, resolved=PIGA),
            ]
        }
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(
                    genome=NF54, target=ALIASED_PAIR, sampled=True, status="screened"
                )
            ],
        )
        (pair,) = await repo.findings(run_id, FindingFilter())
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
        await repo.try_evidence(pair.id, "confirmation")
        await repo.save_evidence(
            pair.id,
            ConfirmationEvidence(confirmation=PseudogeneConfirmation(result=resolved)),
            requests=2,
        )
        await session.commit()
    return owner, run_id, pair.id


async def halted_run() -> tuple[RunOwner, UUID]:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.set_deadline(run_id, DEADLINE)
        await repo.set_status(run_id, "running")
        await repo.set_halted(run_id, SIGN_IN_NEEDED)
        await session.commit()
    return owner, run_id


async def finished_run_with_an_unread_finding() -> tuple[RunOwner, UUID]:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    (target,) = SCOPE.targets
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(
            run_id,
            [
                NewFinding(
                    genome=NF54,
                    target=target,
                    sampled=True,
                    status="unread",
                    message=NOT_READ,
                )
            ],
        )
        repo = AuditRepository(session)
        await repo.set_deadline(run_id, DEADLINE)
        for stage in ("collect", "screen", "confirm", "tie_break"):
            await repo.finish_stage(run_id, stage)
        await repo.set_status(run_id, "finished")
        await session.commit()
    return owner, run_id


async def delete_conversation(conversation_id: UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            delete(Conversation).where(Conversation.id == conversation_id)
        )
        await session.commit()
