"""A finding of the intron check stores its check, its error type and the verdict it read."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.audit.confirmations import IntronConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.tests._support.audit_introns import INTRON_GENE, intron_audit
from pathfinder.tests.integration.persistence._audit_runs import new_owner

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_GENOME = "Examplea alpha A"
_TARGET = SingleGeneTarget(check="intron_support", genes=(INTRON_GENE,))


async def test_an_intron_finding_stores_its_check_and_error_type(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    replaced = IntronConfirmation(result=intron_audit("UNSUPPORTED_REPLACED"))
    async with session_maker() as session:
        user_id, conversation_id = await new_owner(session)
        run_id = await AuditRepository(session).create_run(
            user_id=user_id,
            conversation_id=conversation_id,
            scope=AuditScope(site_id="toxodb", targets=(_TARGET,)),
            seed=7,
        )
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(
                    genome=_GENOME, target=_TARGET, sampled=True, status="screened"
                )
            ],
        )
        (found,) = await repo.findings(run_id, FindingFilter())
        await repo.try_finding(found.id)
        await repo.settle_finding(
            found.id,
            SettledFinding(
                status="confirmed",
                genome=_GENOME,
                error_type="shifted_splice_site",
                certainty="medium",
                requests=3,
            ),
        )
        await repo.save_evidence(
            found.id, ConfirmationEvidence(confirmation=replaced), requests=0
        )
        await session.commit()

    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        (stored,) = await repo.findings(
            run_id, FindingFilter(checks=("intron_support",))
        )
        (evidence,) = await repo.evidence(run_id, [stored.id])

    assert (stored.target, stored.status, stored.error_type, stored.certainty) == (
        _TARGET,
        "confirmed",
        "shifted_splice_site",
        "medium",
    )
    assert evidence.payload == ConfirmationEvidence(confirmation=replaced)
