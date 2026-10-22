"""What a named finding is weighed by, and where a contrary tie-break moves its error."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.audit.findings import Certainty, ErrorType
from pathfinder.domain.audit.rates import Weighing
from pathfinder.persistence.models import AuditEvidence, AuditFinding

__all__ = ["AuditWeighingRepository"]


class AuditWeighingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def set_impact(self, finding_id: int, weighing: Weighing) -> None:
        await self.session.execute(
            update(AuditFinding)
            .where(AuditFinding.id == finding_id)
            .values(
                impact=weighing.impact,
                weighing=weighing.model_dump(by_alias=True, mode="json"),
            )
        )

    async def remodel(
        self, finding_id: int, error_type: ErrorType, certainty: Certainty, genome: str
    ) -> None:
        await self.session.execute(
            update(AuditFinding)
            .where(
                AuditFinding.id == finding_id,
                AuditFinding.status == "confirmed",
                AuditFinding.error_type.is_not(None),
            )
            .values(error_type=error_type, certainty=certainty)
            .values(genome=genome, paired_genome=genome)
        )
        await self.session.execute(
            update(AuditEvidence)
            .where(
                AuditEvidence.finding_id == finding_id,
                AuditEvidence.kind == "gene_evidence",
                AuditEvidence.status != "trying",
            )
            .values(status="pending", payload=None, message=None)
        )

    async def reset_readings(self, run_id: UUID) -> list[int]:
        found = await self.session.scalars(
            select(AuditEvidence.finding_id).where(
                AuditEvidence.kind == "gene_evidence",
                AuditEvidence.status == "pending",
                AuditEvidence.finding_id.in_(
                    select(AuditFinding.id).where(AuditFinding.run_id == run_id)
                ),
            )
        )
        return list(found)
