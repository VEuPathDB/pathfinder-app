"""Stage four: the relatives' lengths beside each confirmed length error, and the gene records
of each named finding, which set its impact."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from assistant_core.platform.db import async_session_factory
from veupathdb_mcp.audit import (
    GeneLengthAudit,
    GeneRow,
    GroupMember,
    orthologs_of,
    record_rows,
    relatives_of,
    tie_break,
)

from pathfinder.domain.audit.confirmations import LengthConfirmation
from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    EvidenceKind,
    EvidencePayload,
    RelativesEvidence,
    remodeled_by_side,
)
from pathfinder.persistence.models import (
    AuditEvidenceRecord,
    AuditFindingRecord,
    AuditRunRecord,
)
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.persistence.repositories.audit_weighings import AuditWeighingRepository
from pathfinder.services.audit.checks import UnitFailure
from pathfinder.services.audit.progress import StageLane, not_read, waiting
from pathfinder.services.audit.units import (
    NOT_READ,
    UNIT_FAILURES,
    ContinueLaterError,
    Waits,
    failure_status,
    in_passes,
    tallied,
)
from pathfinder.services.audit.weighing import References, Subject, read_genes

_NAMED = FindingFilter(statuses=("confirmed",), named=True)
_WEIGHED_CHECKS = frozenset({"gene_length", "gene_split"})
_KINDS: tuple[EvidenceKind, ...] = ("relatives", "gene_evidence")
_OPEN = frozenset({"pending", "unreached", "unread"})
_NO_CONFIRMATION = UnitFailure(
    status="failed", message="no confirmation is stored for this finding"
)
_NO_REFERENCE = UnitFailure(
    status="failed", message="the confirmation names no reference gene"
)


def relatives_evidence(
    reference_gene: str,
    genes: Sequence[str],
    rows: Sequence[GeneRow],
    group: Sequence[GroupMember],
) -> RelativesEvidence | UnitFailure:
    lengths = {row.gene: row.protein_length for row in rows}
    parts = [n for gene in genes if (n := lengths.get(gene))]
    reference = next((row for row in rows if row.gene == reference_gene), None)
    model = next((row for row in rows if row.gene in genes), None)
    if model is None:
        return UnitFailure(
            status="failed",
            message=f"the record reads of {genes[0]} hold no row of the model",
        )
    reference_length = lengths.get(reference_gene)
    organism = None if reference is None else reference.organism
    model_length = sum(parts) if len(parts) == len(genes) else None
    found = None if reference is None else relatives_of(reference, model, group)
    median = None if found is None else found.median
    return RelativesEvidence(
        reference_gene=reference_gene,
        reference_length=reference_length,
        model_length=model_length,
        relatives_median=median,
        relative_lengths={} if found is None else found.lengths,
        relatives_tier=None if found is None else found.tier,
        side=None
        if reference_length is None or model_length is None
        else tie_break(reference_length, model_length, median),
        reference_organism=organism,
    )


@dataclass(frozen=True, kw_only=True)
class _Weighing:
    finding: AuditFindingRecord
    reference: str | UnitFailure


@dataclass(frozen=True, kw_only=True)
class _Reading:
    finding: AuditFindingRecord
    after_relatives: bool


type _Unit = _Weighing | _Reading
type _Read = EvidencePayload | UnitFailure


def _kind(unit: _Unit) -> EvidenceKind:
    match unit:
        case _Weighing():
            return "relatives"
        case _Reading():
            return "gene_evidence"


def _reference(confirmation: EvidencePayload | None) -> str | UnitFailure:
    match confirmation:
        case ConfirmationEvidence(
            confirmation=LengthConfirmation(
                result=GeneLengthAudit(reference_gene=str() as reference)
            )
        ):
            return reference
        case ConfirmationEvidence():
            return _NO_REFERENCE
        case _:
            return _NO_CONFIRMATION


class _Stored:
    def __init__(self, evidence: Sequence[AuditEvidenceRecord]) -> None:
        self.rows = list(evidence)
        self._rows = {(e.finding_id, e.kind): e for e in evidence}

    def _tries(self, finding: AuditFindingRecord, kind: EvidenceKind) -> int:
        row = self._rows.get((finding.id, kind))
        return 0 if row is None else row.attempts

    def _open(self, finding: AuditFindingRecord, kind: EvidenceKind) -> bool:
        row = self._rows.get((finding.id, kind))
        return row is None or row.status in _OPEN

    def pending(
        self, findings: Sequence[AuditFindingRecord], kind: EvidenceKind
    ) -> list[AuditFindingRecord]:
        return sorted(
            (f for f in findings if self._open(f, kind)),
            key=lambda f: (self._tries(f, kind), f.id),
        )


async def _references(run: AuditRunRecord) -> dict[str, bool | None]:
    async with async_session_factory() as session:
        genomes = await AuditRepository(session).genome_states(run.id)
    return {g.organism: g.reference_strain for g in genomes}


async def _open_units(
    run: AuditRunRecord, references: References
) -> tuple[list[_Unit], int]:
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        for kind in _KINDS:
            await repo.sweep_evidence(run.id, kind)
        named = await repo.findings(run.id, _NAMED)
        stored = _Stored(await repo.evidence(run.id, [f.id for f in named]))
        for finding in named:
            weighing = Subject.of(finding, stored.rows).weighing(references)
            if finding.weighing is None and weighing is not None:
                await AuditWeighingRepository(session).set_impact(finding.id, weighing)
        await session.commit()
    lengths = [f for f in named if f.target.check in _WEIGHED_CHECKS]
    weighings: list[_Unit] = [
        _Weighing(
            finding=f,
            reference=_reference(Subject.of(f, stored.rows).confirmation),
        )
        for f in stored.pending(lengths, "relatives")
    ]
    readings: list[_Unit] = [
        _Reading(finding=f, after_relatives=f.target.check in _WEIGHED_CHECKS)
        for f in stored.pending(named, "gene_evidence")
    ]
    return [*weighings, *readings], len(lengths) + len(named)


async def _subject(run: AuditRunRecord, finding_id: int) -> Subject | None:
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        finding = await repo.finding(run.id, finding_id)
        evidence = await repo.evidence(run.id, [finding_id])
    return None if finding is None else Subject.of(finding, evidence)


async def _relatives_open(run: AuditRunRecord, finding_id: int) -> bool:
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).evidence(
            run.id, [finding_id], kinds=("relatives",)
        )
    return not found or found[0].status in _OPEN


async def _read_relatives(
    site_id: str, weighing: _Weighing
) -> RelativesEvidence | UnitFailure:
    genes = weighing.finding.target.genes
    match weighing.reference:
        case UnitFailure() as missing:
            return missing
        case str() as reference_gene:
            named = list(dict.fromkeys([*genes, reference_gene]))
            try:
                group = await orthologs_of(site_id, genes[0])
                rows = await record_rows(site_id, named)
            except UNIT_FAILURES as exc:
                return UnitFailure(status=failure_status(exc), message=str(exc))
            return relatives_evidence(reference_gene, genes, rows, group.members)


async def _read(run: AuditRunRecord, unit: _Unit) -> _Read:
    match unit:
        case _Weighing():
            return await _read_relatives(run.site_id, unit)
        case _Reading(finding=finding):
            subject = await _subject(run, finding.id)
            genes = (finding.target.genes[0],) if subject is None else subject.genes
            return await read_genes(run.site_id, genes)


async def _remodel(
    repo: AuditWeighingRepository, finding: AuditFindingRecord, read: _Read
) -> None:
    match read:
        case RelativesEvidence(side=side, reference_organism=str() as organism):
            remodeled = remodeled_by_side(finding.error_type, side)
        case _:
            return
    if remodeled is None or remodeled.error_type is None or remodeled.certainty is None:
        return
    await repo.remodel(finding.id, remodeled.error_type, remodeled.certainty, organism)


async def _reweigh(
    run: AuditRunRecord, finding_id: int, references: References
) -> None:
    subject = await _subject(run, finding_id)
    weighing = None if subject is None else subject.weighing(references)
    if weighing is not None:
        async with async_session_factory() as session:
            await AuditWeighingRepository(session).set_impact(finding_id, weighing)
            await session.commit()


async def _store(run: AuditRunRecord, unit: _Unit, read: _Read, requests: int) -> None:
    finding_id = unit.finding.id
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        match read:
            case UnitFailure(status=status, message=message):
                await repo.fail_evidence(
                    finding_id,
                    _kind(unit),
                    status=status,
                    message=message,
                    requests=requests,
                )
            case _:
                await repo.save_evidence(finding_id, read, requests=requests)
                await _remodel(AuditWeighingRepository(session), unit.finding, read)
        await AuditRepository(session).count_requests(run.id, "tie_break", requests)
        await session.commit()


async def _weigh(run: AuditRunRecord, unit: _Unit, references: References) -> _Read:
    async with tallied(run.id, "tie_break") as tally:
        read = await _read(run, unit)
    await _store(run, unit, read, tally.count)
    await _reweigh(run, unit.finding.id, references)
    return read


def _said(unit: _Unit, read: _Read) -> tuple[bool, str]:
    named = unit.finding.target.key
    said = f"{named}: gene evidence" if _kind(unit) == "gene_evidence" else f"{named}:"
    match read:
        case UnitFailure(status=status, message=message):
            return status != "unreached", f"{said} {status} ({message})"
        case _:
            return True, f"{said} stored"


async def run_tie_break_stage(
    run: AuditRunRecord, lane: StageLane, waits: Waits
) -> None:
    references = await _references(run)
    pending, total = await _open_units(run, references)
    done = total - len(pending)

    async def attempt(unit: _Unit) -> bool:
        nonlocal done
        match unit:
            case _Reading(after_relatives=True) if await _relatives_open(
                run, unit.finding.id
            ):
                return False
            case _:
                pass
        async with async_session_factory() as session:
            await AuditFindingRepository(session).try_evidence(
                unit.finding.id, _kind(unit)
            )
            await session.commit()
        answered, said = _said(unit, await _weigh(run, unit, references))
        done += answered
        await lane.update(done=done, total=total, message=said)
        return answered

    async def pausing(seconds: float, left: Sequence[_Unit]) -> None:
        await lane.update(
            done=done,
            total=total,
            message=waiting(run.site_id, seconds, len(left), "finding"),
        )

    async def unread(left: Sequence[_Unit]) -> None:
        async with async_session_factory() as session:
            repo = AuditFindingRepository(session)
            for kind in _KINDS:
                await repo.unread_evidence(
                    [unit.finding.id for unit in left if _kind(unit) == kind],
                    kind,
                    NOT_READ,
                )
            await session.commit()
        await lane.update(
            done=done, total=total, message=not_read(len(left), "finding")
        )

    left = await in_passes(pending, attempt, waits, unread=unread, on_pause=pausing)
    held = [unit.finding.id for unit in left if _kind(unit) == "gene_evidence"]
    async with async_session_factory() as session:
        reset = await AuditWeighingRepository(session).reset_readings(run.id)
    if reset and waits.clock.now() < waits.deadline:
        raise ContinueLaterError(seconds=0.0, next_seconds=waits.first_seconds)
    async with async_session_factory() as session:
        await AuditFindingRepository(session).unread_evidence(
            [*held, *reset], "gene_evidence", NOT_READ
        )
        await session.commit()
