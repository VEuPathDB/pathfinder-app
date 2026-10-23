"""The tallies of an audit run's findings, by the genome that holds each error and by the
genome that screened each sampled candidate, and of its evidence by kind and status."""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from pathfinder.domain.audit.findings import FindingTally
from pathfinder.domain.audit.run_state import EvidenceTally
from pathfinder.persistence.models import AuditEvidence, AuditFinding

__all__ = ["AuditTallyRepository"]


class AuditTallyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _grouped(
        self,
        run_id: UUID,
        genome: InstrumentedAttribute[str],
        *where: ColumnElement[bool],
    ) -> list[FindingTally]:
        grouped = (
            genome,
            AuditFinding.check_name,
            AuditFinding.status,
            AuditFinding.error_type,
            AuditFinding.judged,
            AuditFinding.genome,
        )
        found = await self.session.execute(
            select(*grouped, func.count())
            .where(AuditFinding.run_id == run_id, *where)
            .group_by(*grouped)
            .order_by(*grouped)
        )
        return [
            FindingTally.model_validate(
                {
                    "genome": genome,
                    "check": check,
                    "status": status,
                    "error_type": error_type,
                    "judged": judged,
                    "model_genome": model,
                    "count": count,
                }
            )
            for genome, check, status, error_type, judged, model, count in found
        ]

    async def tally(self, run_id: UUID) -> list[FindingTally]:
        return await self._grouped(run_id, AuditFinding.genome)

    async def sample_tally(
        self, run_id: UUID, target_keys: Collection[str]
    ) -> list[FindingTally]:
        return await self._grouped(
            run_id,
            AuditFinding.screened_genome,
            AuditFinding.target_key.not_in(target_keys),
        )

    async def evidence_tally(self, run_id: UUID) -> list[EvidenceTally]:
        found = await self.session.execute(
            select(AuditEvidence.kind, AuditEvidence.status, func.count())
            .join(AuditFinding, AuditFinding.id == AuditEvidence.finding_id)
            .where(AuditFinding.run_id == run_id)
            .group_by(AuditEvidence.kind, AuditEvidence.status)
            .order_by(AuditEvidence.kind, AuditEvidence.status)
        )
        return [
            EvidenceTally.model_validate(
                {"kind": kind, "status": status, "count": count}
            )
            for kind, status, count in found
        ]
