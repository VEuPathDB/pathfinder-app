from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import ColumnElement, false, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.audit.findings import EvidenceKind
from pathfinder.domain.audit.stages import RunStages, StageName
from pathfinder.persistence.models import (
    AuditEvidence,
    AuditFinding,
    AuditGenome,
    AuditRun,
)
from pathfinder.persistence.rows import rows_changed

_RETRIED = ("unreached", "unread")


class RefusedUnits(BaseModel):
    model_config = ConfigDict(frozen=True)

    genomes: tuple[str, ...] = ()
    findings: tuple[int, ...] = ()
    evidence: tuple[tuple[int, EvidenceKind], ...] = ()

    def and_(self, other: RefusedUnits) -> RefusedUnits:
        return RefusedUnits(
            genomes=(*self.genomes, *other.genomes),
            findings=(*self.findings, *other.findings),
            evidence=(*self.evidence, *other.evidence),
        )


class AuditReopening:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _locked(self, run_id: UUID) -> AuditRun:
        run = await self.session.scalar(
            select(AuditRun)
            .where(AuditRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            msg = f"no audit run {run_id}"
            raise LookupError(msg)
        return run

    async def _reopen(
        self,
        run_id: UUID,
        genomes: ColumnElement[bool],
        findings: ColumnElement[bool],
        evidence: ColumnElement[bool],
    ) -> StageName | None:
        in_run = select(AuditFinding.id).where(AuditFinding.run_id == run_id)
        reopened: list[tuple[StageName, int]] = [
            (
                "collect",
                rows_changed(
                    await self.session.execute(
                        update(AuditGenome)
                        .where(AuditGenome.run_id == run_id, genomes)
                        .values(status="pending", message=None)
                    )
                ),
            ),
            (
                "confirm",
                rows_changed(
                    await self.session.execute(
                        update(AuditFinding)
                        .where(AuditFinding.run_id == run_id, findings)
                        .values(status="screened", message=None)
                    )
                ),
            ),
            (
                "tie_break",
                rows_changed(
                    await self.session.execute(
                        update(AuditEvidence)
                        .where(AuditEvidence.finding_id.in_(in_run), evidence)
                        .values(status="pending", message=None)
                    )
                ),
            ),
        ]
        first: StageName | None = next(
            (stage for stage, count in reopened if count), None
        )
        if first is not None:
            run = await self._locked(run_id)
            run.stages = (
                RunStages.model_validate(run.stages)
                .reopen(first)
                .model_dump(by_alias=True, mode="json")
            )
            run.status = "running"
            run.finished_at = None
            await self.session.flush()
        return first

    async def reopen_refused(
        self, run_id: UUID, refused: RefusedUnits
    ) -> StageName | None:
        evidence = (
            tuple_(AuditEvidence.finding_id, AuditEvidence.kind).in_(refused.evidence)
            if refused.evidence
            else false()
        )
        return await self._reopen(
            run_id,
            (AuditGenome.status == "failed")
            & AuditGenome.organism.in_(refused.genomes),
            (AuditFinding.status == "failed") & AuditFinding.id.in_(refused.findings),
            (AuditEvidence.status == "failed") & evidence,
        )

    async def reopen_unreached(self, run_id: UUID) -> StageName | None:
        return await self._reopen(
            run_id,
            AuditGenome.status.in_(_RETRIED),
            AuditFinding.status.in_(_RETRIED),
            AuditEvidence.status.in_(_RETRIED),
        )
