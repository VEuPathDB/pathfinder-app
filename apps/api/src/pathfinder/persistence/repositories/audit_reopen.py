from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.audit.stages import RunStages, StageName
from pathfinder.persistence.models import (
    AuditEvidence,
    AuditFinding,
    AuditGenome,
    AuditRun,
)
from pathfinder.persistence.rows import rows_changed

_RETRIED = ("unreached", "unread")


def _flagged(
    unit: type[AuditGenome | AuditFinding | AuditEvidence],
) -> ColumnElement[bool]:
    return (unit.status == "failed") & unit.refused_by_sign_in.is_(True)


def _reopened(
    unit: type[AuditGenome | AuditFinding | AuditEvidence],
) -> ColumnElement[bool]:
    return (unit.status != "failed") & unit.refused_by_sign_in.is_(True)


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

    async def reopen_refused(self, run_id: UUID) -> StageName | None:
        return await self._reopen(
            run_id,
            _flagged(AuditGenome),
            _flagged(AuditFinding),
            _flagged(AuditEvidence),
        )

    async def reopen_unreached(self, run_id: UUID) -> StageName | None:
        return await self._reopen(
            run_id,
            AuditGenome.status.in_(_RETRIED) | _flagged(AuditGenome),
            AuditFinding.status.in_(_RETRIED) | _flagged(AuditFinding),
            AuditEvidence.status.in_(_RETRIED) | _flagged(AuditEvidence),
        )

    async def clear_refusals(self, run_id: UUID) -> None:
        in_run = select(AuditFinding.id).where(AuditFinding.run_id == run_id)
        await self.session.execute(
            update(AuditGenome)
            .where(AuditGenome.run_id == run_id, _flagged(AuditGenome))
            .values(refused_by_sign_in=False)
        )
        await self.session.execute(
            update(AuditFinding)
            .where(AuditFinding.run_id == run_id, _flagged(AuditFinding))
            .values(refused_by_sign_in=False)
        )
        await self.session.execute(
            update(AuditEvidence)
            .where(AuditEvidence.finding_id.in_(in_run), _flagged(AuditEvidence))
            .values(refused_by_sign_in=False)
        )

    async def holds_reopened_refusals(self, run_id: UUID) -> bool:
        in_run = select(AuditFinding.id).where(AuditFinding.run_id == run_id)
        found = (
            await self.session.scalar(
                select(func.count())
                .select_from(AuditGenome)
                .where(AuditGenome.run_id == run_id, _reopened(AuditGenome))
            ),
            await self.session.scalar(
                select(func.count())
                .select_from(AuditFinding)
                .where(AuditFinding.run_id == run_id, _reopened(AuditFinding))
            ),
            await self.session.scalar(
                select(func.count())
                .select_from(AuditEvidence)
                .where(AuditEvidence.finding_id.in_(in_run), _reopened(AuditEvidence))
            ),
        )
        return any(found)

    async def settled_units(self, run_id: UUID) -> int:
        in_run = select(AuditFinding.id).where(AuditFinding.run_id == run_id)
        counted = (
            await self.session.scalar(
                select(func.count())
                .select_from(AuditGenome)
                .where(AuditGenome.run_id == run_id, AuditGenome.status == "collected")
            ),
            await self.session.scalar(
                select(func.count())
                .select_from(AuditFinding)
                .where(
                    AuditFinding.run_id == run_id, AuditFinding.status == "confirmed"
                )
            ),
            await self.session.scalar(
                select(func.count())
                .select_from(AuditEvidence)
                .where(
                    AuditEvidence.finding_id.in_(in_run),
                    AuditEvidence.status == "stored",
                )
            ),
        )
        return sum(count or 0 for count in counted)

    async def refused_count(self, run_id: UUID) -> int:
        in_run = select(AuditFinding.id).where(AuditFinding.run_id == run_id)
        counted = (
            await self.session.scalar(
                select(func.count())
                .select_from(AuditGenome)
                .where(AuditGenome.run_id == run_id, _flagged(AuditGenome))
            ),
            await self.session.scalar(
                select(func.count())
                .select_from(AuditFinding)
                .where(AuditFinding.run_id == run_id, _flagged(AuditFinding))
            ),
            await self.session.scalar(
                select(func.count())
                .select_from(AuditEvidence)
                .where(AuditEvidence.finding_id.in_(in_run), _flagged(AuditEvidence))
            ),
        )
        return sum(count or 0 for count in counted)
