"""The rows of an audit run and its collected genomes, and the stage state they share."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from assistant_core.platform.context import calling_application
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import ColumnElement, Select, case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, defer
from veupathdb_mcp.audit import GeneRow, GenomePriority

from pathfinder.domain.audit.findings import MAX_STOPS
from pathfinder.domain.audit.scope import AuditScope, GenomeRole
from pathfinder.domain.audit.stages import RunStages, RunStatus, StageName
from pathfinder.persistence.models import (
    AuditEvidence,
    AuditFinding,
    AuditGenome,
    AuditGenomeState,
    AuditRun,
    AuditRunRecord,
)
from pathfinder.persistence.rows import rows_changed

__all__ = [
    "STOPPED_MESSAGE",
    "AuditRepository",
    "CollectedGenome",
    "UnitNotOpenError",
    "stopped_message",
]

STOPPED_MESSAGE = f"the worker stopped during this unit {MAX_STOPS} times"


def stopped_message(message: InstrumentedAttribute[str | None]) -> ColumnElement[str]:
    return func.concat_ws("; ", STOPPED_MESSAGE, message)


_GENES = TypeAdapter(list[GeneRow])
_OPEN = ("pending", "unreached", "unread")
_RETRIED = ("unreached", "unread")


def _stages(stages: RunStages) -> JSONObject:
    return stages.model_dump(by_alias=True, mode="json")


def _read_once(genome: CollectedGenome) -> dict[str, JSONObject | bool]:
    kept: dict[str, JSONObject | bool] = {}
    if genome.priority is not None:
        kept["priority"] = genome.priority.model_dump(by_alias=True, mode="json")
    if genome.reference_strain is not None:
        kept["reference_strain"] = genome.reference_strain
    return kept


class UnitNotOpenError(LookupError):
    @classmethod
    def unless(cls, changed: object | None, unit: str, wanted: str) -> None:
        if changed is None:
            msg = f"{unit} is not {wanted}"
            raise cls(msg)


class CollectedGenome(BaseModel):
    model_config = ConfigDict(frozen=True)

    organism: str
    status: Literal["collected", "failed", "unreached"]
    genes: list[GeneRow] = Field(default_factory=list)
    requests: int = Field(default=0, ge=0)
    message: str | None = None
    priority: GenomePriority | None = None
    reference_strain: bool | None = None


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self, *, user_id: UUID, conversation_id: UUID, scope: AuditScope, seed: int
    ) -> UUID:
        run = AuditRun(
            user_id=user_id,
            conversation_id=conversation_id,
            site_id=scope.site_id,
            scope=scope.model_dump(by_alias=True, mode="json"),
            seed=seed,
            stages=_stages(RunStages()),
        )
        self.session.add(run)
        await self.session.flush()
        return run.id

    def _owned(self, user_id: UUID) -> Select[tuple[AuditRun]]:
        return select(AuditRun).where(
            AuditRun.user_id == user_id,
            AuditRun.application_id == calling_application(),
        )

    async def run(self, run_id: UUID, *, user_id: UUID) -> AuditRunRecord | None:
        found = await self.session.scalar(
            self._owned(user_id).where(AuditRun.id == run_id)
        )
        return None if found is None else AuditRunRecord.model_validate(found)

    async def stored_run(self, run_id: UUID) -> AuditRunRecord | None:
        found = await self.session.scalar(
            select(AuditRun)
            .where(AuditRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        return None if found is None else AuditRunRecord.model_validate(found)

    async def resumable_runs(self) -> list[AuditRunRecord]:
        started = (AuditRun.status == "running") | (
            (AuditRun.status == "planned") & AuditRun.deadline_at.is_not(None)
        )
        found = await self.session.scalars(
            select(AuditRun).where(started).order_by(AuditRun.id)
        )
        return [AuditRunRecord.model_validate(run) for run in found]

    async def runs(self, *, user_id: UUID) -> list[AuditRunRecord]:
        found = await self.session.scalars(
            self._owned(user_id).order_by(AuditRun.created_at.desc(), AuditRun.id)
        )
        return [AuditRunRecord.model_validate(run) for run in found]

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

    async def set_status(self, run_id: UUID, status: RunStatus) -> None:
        run = await self._locked(run_id)
        run.status = status
        run.finished_at = datetime.now(UTC) if status == "finished" else None
        await self.session.flush()

    async def set_release(self, run_id: UUID, release: str) -> None:
        run = await self._locked(run_id)
        run.release = release
        await self.session.flush()

    async def set_deadline(self, run_id: UUID, deadline_at: datetime) -> None:
        run = await self._locked(run_id)
        run.deadline_at = deadline_at
        await self.session.flush()

    async def set_token(self, run_id: UUID, sealed: bytes | None) -> None:
        run = await self._locked(run_id)
        run.sealed_token = sealed
        await self.session.flush()

    async def sealed_token(self, run_id: UUID) -> bytes | None:
        return await self.session.scalar(
            select(AuditRun.sealed_token).where(AuditRun.id == run_id)
        )

    async def record_progress(
        self, run_id: UUID, stage: StageName, *, done: int, total: int, message: str
    ) -> None:
        run = await self._locked(run_id)
        run.stages = _stages(
            RunStages.model_validate(run.stages).progress(
                stage, done=done, total=total, message=message
            )
        )
        await self.session.flush()

    async def count_requests(
        self, run_id: UUID, stage: StageName, requests: int
    ) -> None:
        run = await self._locked(run_id)
        run.stages = _stages(
            RunStages.model_validate(run.stages).count(stage, requests)
        )
        await self.session.flush()

    async def finish_stage(self, run_id: UUID, stage: StageName) -> None:
        run = await self._locked(run_id)
        run.stages = _stages(RunStages.model_validate(run.stages).finish(stage))
        await self.session.flush()

    async def note_target_failure(self, run_id: UUID, message: str) -> None:
        run = await self._locked(run_id)
        run.stages = _stages(
            RunStages.model_validate(run.stages).note_target_failure(message)
        )
        await self.session.flush()

    async def set_halted(self, run_id: UUID, reason: str | None) -> None:
        run = await self._locked(run_id)
        run.stages = _stages(RunStages.model_validate(run.stages).halt(reason))
        await self.session.flush()

    async def release_trying(self, run_id: UUID) -> None:
        await self.session.execute(
            update(AuditGenome)
            .where(AuditGenome.run_id == run_id, AuditGenome.status == "trying")
            .values(status="pending")
        )
        await self.session.execute(
            update(AuditFinding)
            .where(AuditFinding.run_id == run_id, AuditFinding.status == "trying")
            .values(status="screened")
        )
        await self.session.execute(
            update(AuditEvidence)
            .where(
                AuditEvidence.status == "trying",
                AuditEvidence.finding_id.in_(
                    select(AuditFinding.id).where(AuditFinding.run_id == run_id)
                ),
            )
            .values(status="pending")
        )

    async def note_on_trying(self, run_id: UUID, message: str) -> None:
        in_run = select(AuditFinding.id).where(AuditFinding.run_id == run_id)
        await self.session.execute(
            update(AuditGenome)
            .where(AuditGenome.run_id == run_id, AuditGenome.status == "trying")
            .values(message=message)
        )
        await self.session.execute(
            update(AuditFinding)
            .where(AuditFinding.run_id == run_id, AuditFinding.status == "trying")
            .values(message=message)
        )
        await self.session.execute(
            update(AuditEvidence)
            .where(
                AuditEvidence.status == "trying", AuditEvidence.finding_id.in_(in_run)
            )
            .values(message=message)
        )

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
            run.stages = _stages(RunStages.model_validate(run.stages).reopen(first))
            run.status = "running"
            run.finished_at = None
            await self.session.flush()
        return first

    async def reopen_refused(
        self, run_id: UUID, messages: Sequence[str]
    ) -> StageName | None:
        if not messages:
            return None
        return await self._reopen(
            run_id,
            (AuditGenome.status == "failed") & AuditGenome.message.in_(messages),
            (AuditFinding.status == "failed") & AuditFinding.message.in_(messages),
            (AuditEvidence.status == "failed") & AuditEvidence.message.in_(messages),
        )

    async def reopen_unreached(self, run_id: UUID) -> StageName | None:
        return await self._reopen(
            run_id,
            AuditGenome.status.in_(_RETRIED),
            AuditFinding.status.in_(_RETRIED),
            AuditEvidence.status.in_(_RETRIED),
        )

    async def add_genomes(
        self, run_id: UUID, roles: Sequence[tuple[str, GenomeRole]]
    ) -> None:
        if not roles:
            return
        await self.session.execute(
            insert(AuditGenome)
            .values(
                [
                    {"run_id": run_id, "organism": o, "role": r, "status": "pending"}
                    for o, r in roles
                ]
            )
            .on_conflict_do_nothing(constraint="uq_audit_genomes_run_organism")
        )

    def _states(self, run_id: UUID) -> Select[tuple[AuditGenome]]:
        return (
            select(AuditGenome)
            .options(defer(AuditGenome.genes))
            .where(AuditGenome.run_id == run_id)
            .order_by(AuditGenome.id)
            .execution_options(populate_existing=True)
        )

    async def genome_states(self, run_id: UUID) -> list[AuditGenomeState]:
        found = await self.session.scalars(self._states(run_id))
        return [AuditGenomeState.model_validate(genome) for genome in found]

    async def open_genomes(self, run_id: UUID) -> list[AuditGenomeState]:
        found = await self.session.scalars(
            self._states(run_id)
            .where(AuditGenome.status.in_(_OPEN))
            .order_by(None)
            .order_by(AuditGenome.attempts, AuditGenome.id)
        )
        return [AuditGenomeState.model_validate(genome) for genome in found]

    async def unread_genomes(
        self, run_id: UUID, organisms: Sequence[str], message: str
    ) -> None:
        await self.session.execute(
            update(AuditGenome)
            .where(
                AuditGenome.run_id == run_id,
                AuditGenome.organism.in_(organisms),
                AuditGenome.status == "pending",
            )
            .values(
                status=case((AuditGenome.attempts == 0, "unread"), else_="unreached"),
                message=func.coalesce(AuditGenome.message, message),
            )
        )

    async def try_genome(self, run_id: UUID, organism: str) -> None:
        tried = await self.session.scalar(
            update(AuditGenome)
            .where(
                AuditGenome.run_id == run_id,
                AuditGenome.organism == organism,
                AuditGenome.status.in_(_OPEN),
            )
            .values(status="trying", attempts=AuditGenome.attempts + 1)
            .returning(AuditGenome.id)
        )
        UnitNotOpenError.unless(tried, f"genome {organism} of run {run_id}", "open")

    async def save_genome(self, run_id: UUID, genome: CollectedGenome) -> None:
        saved = await self.session.scalar(
            update(AuditGenome)
            .where(
                AuditGenome.run_id == run_id,
                AuditGenome.organism == genome.organism,
                AuditGenome.status == "trying",
            )
            .values(
                status=genome.status,
                gene_count=len(genome.genes),
                genes=_GENES.dump_python(genome.genes, mode="json"),
                requests=AuditGenome.requests + genome.requests,
                message=genome.message,
                **_read_once(genome),
            )
            .returning(AuditGenome.id)
        )
        UnitNotOpenError.unless(
            saved, f"genome {genome.organism} of run {run_id}", "being tried"
        )

    async def sweep_genomes(self, run_id: UUID) -> None:
        stopped = AuditGenome.stopped + 1
        await self.session.execute(
            update(AuditGenome)
            .where(AuditGenome.run_id == run_id, AuditGenome.status == "trying")
            .values(
                stopped=stopped,
                status=case((stopped >= MAX_STOPS, "failed"), else_="pending"),
                message=case(
                    (stopped >= MAX_STOPS, stopped_message(AuditGenome.message)),
                    else_=AuditGenome.message,
                ),
            )
        )

    async def collected_genome(self, run_id: UUID, organism: str) -> list[GeneRow]:
        genes = await self.session.scalar(
            select(AuditGenome.genes).where(
                AuditGenome.run_id == run_id,
                AuditGenome.organism == organism,
                AuditGenome.status == "collected",
            )
        )
        return [] if genes is None else _GENES.validate_python(genes)

    async def delete_runs(self, *, user_id: UUID, site_id: str | None) -> int:
        statement = delete(AuditRun).where(
            AuditRun.user_id == user_id,
            AuditRun.application_id == calling_application(),
        )
        if site_id == "":
            msg = "a purge names a site, or None for every site"
            raise ValueError(msg)
        if site_id is not None:
            statement = statement.where(AuditRun.site_id == site_id)
        return rows_changed(await self.session.execute(statement))
