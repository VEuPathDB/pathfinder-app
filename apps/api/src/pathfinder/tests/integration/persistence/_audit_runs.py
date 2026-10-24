"""Owned audit runs, and the unit states of one, that the audit repository tests read."""

from __future__ import annotations

from uuid import UUID, uuid4

from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.audit.findings import RelativesEvidence
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget, SingleGeneTarget
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests._support.audit import NF54, NF54_PIGA, PIGA

PAIR = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
SHORT = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
SCOPE = AuditScope(site_id="plasmodb", targets=(PAIR,))
RELATIVES = RelativesEvidence(
    reference_gene=PIGA,
    reference_length=461,
    model_length=461,
    relatives_median=460.0,
    relative_lengths={},
    relatives_tier=None,
    side=None,
    reference_organism=None,
)
UNREACHED = "plasmodb did not answer"

UnitState = tuple[str, int, int, str | None]


async def new_owner(session: AsyncSession) -> tuple[UUID, UUID]:
    user_id, conversation_id = uuid4(), uuid4()
    session.add(User(id=user_id))
    await session.flush()
    session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conversation_id,
            user_id=user_id,
            site_id="plasmodb",
            name="",
        )
    )
    await session.flush()
    return user_id, conversation_id


async def new_run(
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    async with session_maker() as session:
        user_id, conversation_id = await new_owner(session)
        run_id = await AuditRepository(session).create_run(
            user_id=user_id, conversation_id=conversation_id, scope=SCOPE, seed=7
        )
        await session.commit()
    return user_id, run_id


async def one_finding(
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[UUID, int]:
    _, run_id = await new_run(session_maker)
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [NewFinding(genome=NF54, target=PAIR, sampled=True, status="screened")],
        )
        (finding,) = await repo.findings(run_id, FindingFilter())
        await session.commit()
    return run_id, finding.id


async def unit_states(session: AsyncSession, run_id: UUID) -> dict[str, UnitState]:
    runs, findings = AuditRepository(session), AuditFindingRepository(session)
    found = await findings.findings(run_id, FindingFilter())
    evidence = await findings.evidence(run_id, [f.id for f in found])
    keys = {f.id: f.target.key for f in found}
    return {
        **{
            g.organism: (g.status, g.attempts, g.stopped, g.message)
            for g in await runs.genome_states(run_id)
        },
        **{f.target.key: (f.status, f.attempts, f.stopped, f.message) for f in found},
        **{
            f"{keys[e.finding_id]}/{e.kind}": (
                e.status,
                e.attempts,
                e.stopped,
                e.message,
            )
            for e in evidence
        },
    }
