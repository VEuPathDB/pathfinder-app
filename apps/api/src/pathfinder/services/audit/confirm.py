"""Stage three: each sampled candidate and gene target checked by its library check."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from assistant_core.platform.db import async_session_factory
from veupathdb_mcp.audit import gene_rows

from pathfinder.domain.audit.findings import (
    Confirmation,
    ConfirmationEvidence,
    StrainConfirmation,
    classify_confirmation,
)
from pathfinder.domain.audit.scope import paired_genome
from pathfinder.persistence.models import AuditFindingRecord, AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    SettledFinding,
)
from pathfinder.services.audit.checks import UnitFailure, confirm_target
from pathfinder.services.audit.progress import StageLane, not_read, waiting
from pathfinder.services.audit.units import (
    NOT_READ,
    UNIT_FAILURES,
    Waits,
    failure_status,
    in_passes,
    tallied,
)

_SAMPLED = FindingFilter(sampled=True)
_OPEN = FindingFilter(sampled=True, statuses=("screened", "unreached", "unread"))


@dataclass(frozen=True, kw_only=True)
class _Placed:
    screened: str | None
    model: str | None = None
    paired: str | None = None


async def _organisms(
    site_id: str, genes: Sequence[str]
) -> dict[str, str] | UnitFailure:
    try:
        rows = await gene_rows(site_id, list(genes))
    except UNIT_FAILURES as exc:
        return UnitFailure(status=failure_status(exc), message=str(exc))
    organisms = {row.gene: row.organism for row in rows}
    missing = [name for name in genes if name not in organisms]
    if missing:
        return UnitFailure(
            status="failed",
            message=f"{site_id} serves no gene row for {', '.join(missing)}",
        )
    return organisms


async def _placed(site_id: str, finding: AuditFindingRecord) -> _Placed | UnitFailure:
    if finding.genome:
        return _Placed(screened=finding.genome)
    target = finding.target
    match await _organisms(site_id, target.genes):
        case UnitFailure() as unplaced:
            return unplaced
        case organisms:
            return _Placed(
                screened=organisms[target.genes[0]],
                paired=paired_genome(target, organisms),
            )


async def _in_model_genome(
    site_id: str, reached: Confirmation, placed: _Placed
) -> tuple[Confirmation | UnitFailure, _Placed]:
    match (classify_confirmation(reached).model_role, reached):
        case ("reference", StrainConfirmation(result=result)):
            gene = result.reference_gene
        case _:
            return reached, placed
    match await _organisms(site_id, [gene]):
        case UnitFailure() as unplaced:
            return unplaced, placed
        case organisms:
            organism = organisms[gene]
            return reached, replace(placed, model=organism, paired=organism)


async def _check(
    site_id: str, finding: AuditFindingRecord
) -> tuple[Confirmation | UnitFailure, _Placed]:
    match await _placed(site_id, finding):
        case UnitFailure() as unplaced:
            return unplaced, _Placed(screened=None)
        case _Placed() as placed:
            pass
    match await confirm_target(site_id, finding.target):
        case UnitFailure() as failed:
            return failed, placed
        case reached:
            return await _in_model_genome(site_id, reached, placed)


def _settled(
    reached: Confirmation | UnitFailure, requests: int, placed: _Placed
) -> tuple[SettledFinding, ConfirmationEvidence | None, str]:
    genome, screened, paired = (
        placed.model or placed.screened,
        placed.screened,
        placed.paired,
    )
    match reached:
        case UnitFailure(status=status, message=message):
            failed = SettledFinding(
                status=status,
                genome=genome,
                screened_genome=screened,
                paired_genome=paired,
                requests=requests,
                message=message,
            )
            return failed, None, f"{status} ({message})"
        case _:
            named = classify_confirmation(reached)
            confirmed = SettledFinding(
                status="confirmed",
                genome=genome,
                screened_genome=screened,
                paired_genome=paired,
                error_type=named.error_type,
                certainty=named.certainty,
                judged=named.judged,
                requests=requests,
                message=named.message,
            )
            evidence = ConfirmationEvidence(confirmation=reached)
            return confirmed, evidence, reached.verdict


async def _settle(
    finding: AuditFindingRecord,
    checked: tuple[Confirmation | UnitFailure, _Placed],
    requests: int,
) -> tuple[SettledFinding, str]:
    reached, placed = checked
    settled, evidence, said = _settled(reached, requests, placed)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.settle_finding(finding.id, settled)
        if evidence is not None:
            await repo.save_evidence(finding.id, evidence, requests=0)
        await AuditRepository(session).count_requests(
            finding.run_id, "confirm", requests
        )
        await session.commit()
    return settled, said


async def _open_findings(run: AuditRunRecord) -> tuple[list[AuditFindingRecord], int]:
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.sweep_findings(run.id)
        found = await repo.findings(run.id, _OPEN)
        total = await repo.count_findings(run.id, _SAMPLED)
        await session.commit()
    return sorted(found, key=lambda f: (f.attempts, f.id)), total


async def run_confirm_stage(run: AuditRunRecord, lane: StageLane, waits: Waits) -> None:
    pending, total = await _open_findings(run)
    done = total - len(pending)

    async def attempt(finding: AuditFindingRecord) -> bool:
        nonlocal done
        async with async_session_factory() as session:
            await AuditFindingRepository(session).try_finding(finding.id)
            await session.commit()
        async with tallied(run.id, "confirm") as tally:
            checked = await _check(run.site_id, finding)
        settled, said = await _settle(finding, checked, tally.count)
        answered = settled.status != "unreached"
        done += answered
        await lane.update(
            done=done, total=total, message=f"{finding.target.key}: {said}"
        )
        return answered

    async def pausing(seconds: float, left: Sequence[AuditFindingRecord]) -> None:
        await lane.update(
            done=done,
            total=total,
            message=waiting(run.site_id, seconds, len(left), "finding"),
        )

    async def unread(left: Sequence[AuditFindingRecord]) -> None:
        async with async_session_factory() as session:
            await AuditFindingRepository(session).unread_findings(
                [finding.id for finding in left], NOT_READ
            )
            await session.commit()
        await lane.update(
            done=done, total=total, message=not_read(len(left), "finding")
        )

    await in_passes(pending, attempt, waits, unread=unread, on_pause=pausing)
