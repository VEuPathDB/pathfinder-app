"""The tallies of an audit run's findings: by the genome that holds each error, and by the
genome that screened each sampled candidate."""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from pathfinder.domain.audit.findings import FindingTally
from pathfinder.persistence.models import AuditFinding

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
