"""Stage one: each genome's gene report, its BUSCO scores, whether it is its species' reference
strain, and the site's release, read once and stored."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import pydantic
from assistant_core.platform.db import async_session_factory
from veupathdb.wdk import WDKAnswer
from veupathdb_mcp.audit import (
    GENOME_ATTRIBUTES,
    GeneRow,
    GenomePriority,
    genes_of_genome,
    genome_priorities,
    organism_report,
    provenance_of,
)

from pathfinder.persistence.models import AuditGenomeState, AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository, CollectedGenome
from pathfinder.platform.metrics import counting_wdk_requests
from pathfinder.services.audit.checks import UnitFailure
from pathfinder.services.audit.progress import StageLane, not_read, waiting
from pathfinder.services.audit.units import (
    NOT_READ,
    UNIT_FAILURES,
    Waits,
    failure_status,
    halt_when_signed_out,
    in_passes,
    tallied,
)
from pathfinder.services.wdk_build import site_build


async def _read_release(run: AuditRunRecord) -> str | None:
    release: str | None = None
    failure: Exception | None = None
    with counting_wdk_requests() as tally:
        try:
            release = await site_build(run.site_id)
        except UNIT_FAILURES as exc:
            failure = exc
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        if release is not None:
            await repo.set_release(run.id, release)
        await repo.count_requests(run.id, "collect", tally.count)
        await session.commit()
    if failure is None:
        return None
    halt_when_signed_out(failure)
    return str(failure)


class _Scores:
    def __init__(self, site_id: str) -> None:
        self.site_id = site_id
        self.read: list[GenomePriority] | UnitFailure | None = None

    async def _report(self) -> list[GenomePriority] | UnitFailure:
        try:
            return await genome_priorities(self.site_id)
        except UNIT_FAILURES as exc:
            return UnitFailure(status=failure_status(exc), message=str(exc))

    async def of(self, state: AuditGenomeState) -> GenomePriority | UnitFailure | None:
        if state.role != "audited" or state.priority is not None:
            return None
        if self.read is None:
            self.read = await self._report()
        match self.read:
            case UnitFailure():
                return self.read
            case served:
                return next((p for p in served if p.organism == state.organism), None)


class _Provenances:
    def __init__(self, site_id: str) -> None:
        self.site_id = site_id
        self.read: WDKAnswer | UnitFailure | None = None

    async def _report(self) -> WDKAnswer | UnitFailure:
        try:
            return await organism_report(self.site_id, GENOME_ATTRIBUTES)
        except UNIT_FAILURES as exc:
            return UnitFailure(status=failure_status(exc), message=str(exc))

    def _served(self, answer: WDKAnswer, organism: str) -> bool | UnitFailure:
        try:
            provenance = provenance_of(answer, organism)
        except pydantic.ValidationError:
            message = (
                f"the organism record of {organism} on {self.site_id} is not readable"
            )
            return UnitFailure(status="failed", message=message)
        if provenance is None:
            message = f"{organism} names no genome of {self.site_id}"
            return UnitFailure(status="failed", message=message)
        return provenance.reference_strain

    async def reference_strain(
        self, state: AuditGenomeState
    ) -> bool | UnitFailure | None:
        if state.role != "audited" or state.reference_strain is not None:
            return None
        if self.read is None:
            self.read = await self._report()
        match self.read:
            case UnitFailure():
                return self.read
            case answer:
                return self._served(answer, state.organism)


@dataclass(frozen=True)
class _Reads:
    scores: _Scores
    provenances: _Provenances


@dataclass(kw_only=True)
class _Served:
    priority: GenomePriority | None = None
    reference_strain: bool | None = None
    notes: list[str] = field(default_factory=list)
    unreached: str | None = None

    def genome(
        self,
        organism: str,
        requests: int,
        *,
        status: Literal["collected", "failed", "unreached"],
        message: str | None = None,
        genes: Sequence[GeneRow] = (),
    ) -> CollectedGenome:
        return CollectedGenome(
            organism=organism,
            status=status,
            genes=list(genes),
            requests=requests,
            message=message or "; ".join(self.notes) or None,
            priority=self.priority,
            reference_strain=self.reference_strain,
        )


async def _served(state: AuditGenomeState, reads: _Reads) -> _Served:
    served = _Served()
    match await reads.scores.of(state):
        case UnitFailure(status="unreached", message=message):
            served.unreached = f"BUSCO scores unreached: {message}"
            return served
        case UnitFailure(message=message):
            served.notes.append(f"BUSCO scores failed: {message}")
        case scored:
            served.priority = scored
    match await reads.provenances.reference_strain(state):
        case UnitFailure(status="unreached", message=message):
            served.unreached = f"genome provenance unreached: {message}"
        case UnitFailure(message=message):
            served.notes.append(
                f"genome provenance failed: {message}; its genome use is unknown"
            )
        case reference_strain:
            served.reference_strain = reference_strain
    return served


async def _read_genome(
    run: AuditRunRecord, state: AuditGenomeState, reads: _Reads
) -> CollectedGenome:
    organism = state.organism
    async with tallied(run.id, "collect") as tally:
        served = await _served(state, reads)
        if served.unreached is not None:
            return served.genome(
                organism, tally.count, status="unreached", message=served.unreached
            )
        try:
            rows = await genes_of_genome(run.site_id, organism)
        except UNIT_FAILURES as exc:
            return served.genome(
                organism, tally.count, status=failure_status(exc), message=str(exc)
            )
    return served.genome(organism, tally.count, status="collected", genes=rows)


def _said(genome: CollectedGenome) -> str:
    if genome.status == "collected":
        return f"{genome.organism}: {len(genome.genes)} genes"
    return f"{genome.organism}: {genome.status} ({genome.message})"


async def _open_genomes(run: AuditRunRecord) -> list[AuditGenomeState]:
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run.id, run.scope.roles)
        await repo.sweep_genomes(run.id)
        pending = await repo.open_genomes(run.id)
        await session.commit()
    return pending


async def run_collect_stage(run: AuditRunRecord, lane: StageLane, waits: Waits) -> None:
    pending = await _open_genomes(run)
    first = bool(pending) and all(state.attempts == 0 for state in pending)
    open_time = waits.clock.now() < waits.deadline
    unknown = (
        await _read_release(run)
        if first and open_time and run.release is None
        else None
    )
    known = run.release is not None or (first and unknown is None)
    total = len(run.scope.roles)
    done = total - len(pending)
    reads = _Reads(_Scores(run.site_id), _Provenances(run.site_id))

    async def attempt(state: AuditGenomeState) -> bool:
        nonlocal done
        async with async_session_factory() as session:
            await AuditRepository(session).try_genome(run.id, state.organism)
            await session.commit()
        genome = await _read_genome(run, state, reads)
        async with async_session_factory() as session:
            repo = AuditRepository(session)
            await repo.save_genome(run.id, genome)
            await repo.count_requests(run.id, "collect", genome.requests)
            await session.commit()
        answered = genome.status != "unreached"
        done += answered
        await lane.update(done=done, total=total, message=_said(genome))
        return answered

    async def pausing(seconds: float, left: Sequence[AuditGenomeState]) -> None:
        await lane.update(
            done=done,
            total=total,
            message=waiting(run.site_id, seconds, len(left), "genome"),
        )

    async def unread(left: Sequence[AuditGenomeState]) -> None:
        async with async_session_factory() as session:
            await AuditRepository(session).unread_genomes(
                run.id, [state.organism for state in left], NOT_READ
            )
            await session.commit()
        await lane.update(done=done, total=total, message=not_read(len(left), "genome"))

    await in_passes(pending, attempt, waits, unread=unread, on_pause=pausing)
    if not known and waits.clock.now() < waits.deadline:
        unknown = await _read_release(run)
    if unknown is not None:
        await lane.update(done=done, total=total, message=f"release unknown: {unknown}")
