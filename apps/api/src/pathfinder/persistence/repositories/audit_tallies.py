"""The tallies of an audit run's findings, by the genome that holds each error and by the
genome that screened each sampled candidate, and of its evidence by kind and status."""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from pathfinder.domain.audit.findings import Certainty, ErrorType, FindingTally
from pathfinder.domain.audit.run_state import EvidenceTally
from pathfinder.persistence.models import AuditEvidence, AuditFinding, AuditVerdict

__all__ = ["AuditTallyRepository"]

_ERROR_TYPE_ROW: TypeAdapter[tuple[ErrorType, str, Certainty, int]] = TypeAdapter(
    tuple[ErrorType, str, Certainty, int]
)


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

    async def error_type_tally(
        self, run_id: UUID
    ) -> list[tuple[ErrorType, str, Certainty, int]]:
        reviewed_type = AuditVerdict.verdict["errorType"].astext
        reviewed = reviewed_type.is_not(None)
        error_type = case((reviewed, reviewed_type), else_=AuditFinding.error_type)
        certainty = case(
            (reviewed, AuditVerdict.verdict["certainty"].astext),
            else_=AuditFinding.certainty,
        )
        grouped = (error_type, AuditFinding.genome, certainty)
        found = await self.session.execute(
            select(*grouped, func.count())
            .outerjoin(AuditVerdict, AuditVerdict.finding_id == AuditFinding.id)
            .where(AuditFinding.run_id == run_id, error_type.is_not(None))
            .group_by(*grouped)
            .order_by(*grouped)
        )
        return [_ERROR_TYPE_ROW.validate_python(tuple(row)) for row in found]

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
