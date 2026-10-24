"""The findings of an audit run, the evidence stored for each, and their tally."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from sqlalchemy import Select, case, exists, func, select, update
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.audit.findings import (
    MAX_STOPS,
    Certainty,
    ErrorType,
    EvidenceKind,
    EvidencePayload,
    FindingStatus,
)
from pathfinder.domain.audit.scope import CheckName, GeneTarget
from pathfinder.persistence.models import (
    AuditEvidence,
    AuditEvidenceRecord,
    AuditFinding,
    AuditFindingRecord,
    AuditVerdict,
)
from pathfinder.persistence.repositories.audit import (
    UnitNotOpenError,
    stopped_message,
)

__all__ = ["AuditFindingRepository", "FindingFilter", "NewFinding", "SettledFinding"]

_INSERT_CHUNK = 1000
_PAYLOAD: TypeAdapter[EvidencePayload] = TypeAdapter(EvidencePayload)
_EVIDENCE_KEY = "uq_audit_evidence_finding_kind"
_REVIEWED = exists().where(AuditVerdict.finding_id == AuditFinding.id).label("reviewed")


def _evidence_unit(finding_id: int, kind: str) -> str:
    return f"{kind} evidence of finding {finding_id}"


def _reviewed(finding: AuditFinding, *, reviewed: bool) -> AuditFindingRecord:
    return AuditFindingRecord.model_validate(finding).model_copy(
        update={"reviewed": reviewed}
    )


class NewFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    genome: str
    target: GeneTarget
    sampled: bool
    status: Literal["screened", "unsampled", "unreached", "unread"]
    message: str | None = None
    paired_genome: str | None = None

    @model_validator(mode="after")
    def _sampled_unless_unsampled(self) -> Self:
        if self.sampled == (self.status == "unsampled"):
            msg = "a finding is unsampled exactly when it is not sampled"
            raise ValueError(msg)
        if (self.status in ("unreached", "unread")) != (self.message is not None):
            msg = "a new finding names why exactly when it is unreached"
            raise ValueError(msg)
        return self


class SettledFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["confirmed", "failed", "declined", "unreached"]
    genome: str | None = None
    screened_genome: str | None = None
    paired_genome: str | None = None
    error_type: ErrorType | None = None
    certainty: Certainty | None = None
    judged: bool = True
    requests: int = Field(default=0, ge=0)
    message: str | None = None

    @model_validator(mode="after")
    def _named_error(self) -> Self:
        if (self.error_type is None) != (self.certainty is None):
            msg = "an error type and its certainty are named together"
            raise ValueError(msg)
        if self.error_type is not None and self.status != "confirmed":
            msg = f"only a confirmed finding names an error, not a {self.status} one"
            raise ValueError(msg)
        if not self.judged and (self.status, self.error_type) != ("confirmed", None):
            msg = "only a confirmed finding that names no error can be not judged"
            raise ValueError(msg)
        return self


class FindingFilter(BaseModel):
    model_config = ConfigDict(frozen=True)

    checks: tuple[CheckName, ...] = ()
    statuses: tuple[FindingStatus, ...] = ()
    error_types: tuple[ErrorType, ...] = ()
    genome: str | None = None
    screened_genome: str | None = None
    sampled: bool | None = None
    named: bool | None = None
    keys: tuple[str, ...] | None = None


class AuditFindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_findings(self, run_id: UUID, findings: Sequence[NewFinding]) -> None:
        values = [
            {
                "run_id": run_id,
                "check_name": finding.target.check,
                "genome": finding.genome,
                "target": finding.target.model_dump(by_alias=True, mode="json"),
                "target_key": finding.target.key,
                "screened_genome": finding.genome,
                "paired_genome": finding.paired_genome,
                "sampled": finding.sampled,
                "status": finding.status,
                "message": finding.message,
            }
            for finding in findings
        ]
        for start in range(0, len(values), _INSERT_CHUNK):
            await self.session.execute(
                insert(AuditFinding)
                .values(values[start : start + _INSERT_CHUNK])
                .on_conflict_do_nothing(constraint="uq_audit_findings_run_target")
            )

    async def finding_keys(self, run_id: UUID) -> list[tuple[str, str]]:
        found = await self.session.execute(
            select(AuditFinding.screened_genome, AuditFinding.target_key)
            .where(AuditFinding.run_id == run_id)
            .order_by(AuditFinding.id)
        )
        return [(genome, key) for genome, key in found]

    def _filtered(
        self, run_id: UUID, where: FindingFilter
    ) -> Select[tuple[AuditFinding]]:
        query = select(AuditFinding).where(AuditFinding.run_id == run_id)
        if where.checks:
            query = query.where(AuditFinding.check_name.in_(where.checks))
        if where.statuses:
            query = query.where(AuditFinding.status.in_(where.statuses))
        if where.error_types:
            query = query.where(AuditFinding.error_type.in_(where.error_types))
        if where.genome is not None:
            query = query.where(AuditFinding.genome == where.genome)
        if where.screened_genome is not None:
            query = query.where(AuditFinding.screened_genome == where.screened_genome)
        if where.sampled is not None:
            query = query.where(AuditFinding.sampled.is_(where.sampled))
        if where.named is not None:
            named = AuditFinding.error_type.is_not(None)
            query = query.where(named if where.named else ~named)
        if where.keys is not None:
            query = query.where(AuditFinding.target_key.in_(where.keys))
        return query

    async def findings(
        self,
        run_id: UUID,
        where: FindingFilter,
        *,
        offset: int = 0,
        limit: int | None = None,
        by_impact: bool = False,
    ) -> list[AuditFindingRecord]:
        order = (
            (AuditFinding.impact.desc().nulls_last(), AuditFinding.id)
            if by_impact
            else (AuditFinding.id,)
        )
        query = (
            self._filtered(run_id, where)
            .add_columns(_REVIEWED)
            .order_by(*order)
            .offset(offset)
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        found = await self.session.execute(query)
        return [_reviewed(finding, reviewed=reviewed) for finding, reviewed in found]

    async def count_findings(self, run_id: UUID, where: FindingFilter) -> int:
        counted = await self.session.scalar(
            select(func.count()).select_from(self._filtered(run_id, where).subquery())
        )
        return counted or 0

    async def finding(self, run_id: UUID, finding_id: int) -> AuditFindingRecord | None:
        found = (
            await self.session.execute(
                select(AuditFinding, _REVIEWED)
                .where(AuditFinding.run_id == run_id, AuditFinding.id == finding_id)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        return None if found is None else _reviewed(found[0], reviewed=found[1])

    async def try_finding(self, finding_id: int) -> None:
        tried = await self.session.scalar(
            update(AuditFinding)
            .where(
                AuditFinding.id == finding_id,
                AuditFinding.status.in_(("screened", "unreached", "unread")),
            )
            .values(status="trying", attempts=AuditFinding.attempts + 1)
            .returning(AuditFinding.id)
        )
        UnitNotOpenError.unless(tried, f"finding {finding_id}", "open")

    async def settle_finding(self, finding_id: int, settled: SettledFinding) -> None:
        changed = await self.session.scalar(
            update(AuditFinding)
            .where(AuditFinding.id == finding_id, AuditFinding.status == "trying")
            .values(
                status=settled.status,
                genome=func.coalesce(settled.genome, AuditFinding.genome),
                screened_genome=func.coalesce(
                    func.nullif(AuditFinding.screened_genome, ""),
                    settled.screened_genome,
                    "",
                ),
                paired_genome=func.coalesce(
                    settled.paired_genome, AuditFinding.paired_genome
                ),
                error_type=settled.error_type,
                certainty=settled.certainty,
                judged=settled.judged,
                message=settled.message,
                requests=AuditFinding.requests + settled.requests,
            )
            .returning(AuditFinding.id)
        )
        UnitNotOpenError.unless(changed, f"finding {finding_id}", "being tried")

    async def sweep_findings(self, run_id: UUID) -> None:
        stopped = AuditFinding.stopped + 1
        await self.session.execute(
            update(AuditFinding)
            .where(AuditFinding.run_id == run_id, AuditFinding.status == "trying")
            .values(
                stopped=stopped,
                status=case((stopped >= MAX_STOPS, "failed"), else_="screened"),
                message=case(
                    (stopped >= MAX_STOPS, stopped_message(AuditFinding.message)),
                    else_=AuditFinding.message,
                ),
            )
        )

    async def unread_findings(self, finding_ids: Sequence[int], message: str) -> None:
        await self.session.execute(
            update(AuditFinding)
            .where(
                AuditFinding.id.in_(finding_ids),
                AuditFinding.status == "screened",
            )
            .values(
                status=case((AuditFinding.attempts == 0, "unread"), else_="unreached"),
                message=func.coalesce(AuditFinding.message, message),
            )
        )

    async def unread_evidence(
        self, finding_ids: Sequence[int], kind: EvidenceKind, message: str
    ) -> None:
        if not finding_ids:
            return
        statement = insert(AuditEvidence).values(
            [
                {
                    "finding_id": f,
                    "kind": kind,
                    "status": "unread",
                    "message": message,
                }
                for f in finding_ids
            ]
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                constraint=_EVIDENCE_KEY,
                set_={
                    "status": case(
                        (AuditEvidence.attempts == 0, "unread"), else_="unreached"
                    ),
                    "message": func.coalesce(AuditEvidence.message, message),
                    "updated_at": func.now(),
                },
                where=AuditEvidence.status == "pending",
            )
        )

    async def try_evidence(self, finding_id: int, kind: EvidenceKind) -> None:
        statement = insert(AuditEvidence).values(
            finding_id=finding_id, kind=kind, status="trying", attempts=1
        )
        tried = await self.session.scalar(
            statement.on_conflict_do_update(
                constraint=_EVIDENCE_KEY,
                set_={
                    "status": "trying",
                    "attempts": AuditEvidence.attempts + 1,
                    "updated_at": func.now(),
                },
                where=AuditEvidence.status.in_(("pending", "unreached", "unread")),
            ).returning(AuditEvidence.id)
        )
        UnitNotOpenError.unless(tried, _evidence_unit(finding_id, kind), "open")

    async def save_evidence(
        self, finding_id: int, payload: EvidencePayload, *, requests: int
    ) -> None:
        statement = insert(AuditEvidence).values(
            finding_id=finding_id,
            kind=payload.kind,
            status="stored",
            payload=_PAYLOAD.dump_python(payload, by_alias=True, mode="json"),
            requests=requests,
        )
        await self._settle_evidence(
            statement.on_conflict_do_update(
                constraint=_EVIDENCE_KEY,
                set_={
                    "status": "stored",
                    "payload": statement.excluded.payload,
                    "message": None,
                    "requests": AuditEvidence.requests + requests,
                    "updated_at": func.now(),
                },
                where=AuditEvidence.status == "trying",
            ),
            _evidence_unit(finding_id, payload.kind),
        )

    async def fail_evidence(
        self,
        finding_id: int,
        kind: EvidenceKind,
        *,
        status: Literal["failed", "unreached"],
        message: str,
        requests: int,
    ) -> None:
        statement = insert(AuditEvidence).values(
            finding_id=finding_id,
            kind=kind,
            status=status,
            message=message,
            requests=requests,
        )
        await self._settle_evidence(
            statement.on_conflict_do_update(
                constraint=_EVIDENCE_KEY,
                set_={
                    "status": status,
                    "payload": None,
                    "message": message,
                    "requests": AuditEvidence.requests + requests,
                    "updated_at": func.now(),
                },
                where=AuditEvidence.status == "trying",
            ),
            _evidence_unit(finding_id, kind),
        )

    async def _settle_evidence(self, statement: Insert, unit: str) -> None:
        settled = await self.session.scalar(statement.returning(AuditEvidence.id))
        UnitNotOpenError.unless(settled, unit, "being tried")

    async def sweep_evidence(self, run_id: UUID, kind: EvidenceKind) -> None:
        stopped = AuditEvidence.stopped + 1
        await self.session.execute(
            update(AuditEvidence)
            .where(
                AuditEvidence.kind == kind,
                AuditEvidence.status == "trying",
                AuditEvidence.finding_id.in_(
                    select(AuditFinding.id).where(AuditFinding.run_id == run_id)
                ),
            )
            .values(
                stopped=stopped,
                status=case((stopped >= MAX_STOPS, "failed"), else_="pending"),
                message=case(
                    (stopped >= MAX_STOPS, stopped_message(AuditEvidence.message)),
                    else_=AuditEvidence.message,
                ),
            )
        )

    async def evidence(
        self,
        run_id: UUID,
        finding_ids: Collection[int],
        *,
        kinds: tuple[EvidenceKind, ...] = (),
    ) -> list[AuditEvidenceRecord]:
        if not finding_ids:
            return []
        query = select(AuditEvidence).where(
            AuditEvidence.finding_id.in_(
                select(AuditFinding.id).where(
                    AuditFinding.run_id == run_id, AuditFinding.id.in_(finding_ids)
                )
            )
        )
        if kinds:
            query = query.where(AuditEvidence.kind.in_(kinds))
        found = await self.session.scalars(
            query.order_by(
                AuditEvidence.finding_id, AuditEvidence.id
            ).execution_options(populate_existing=True)
        )
        return [AuditEvidenceRecord.model_validate(row) for row in found]
