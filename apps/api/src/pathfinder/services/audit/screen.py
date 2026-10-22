"""Stage two: the screened genomes' candidates, their pseudogene calls and the gene targets, written as findings."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from veupathdb_mcp.audit import GeneRow, gene_rows

from pathfinder.domain.audit.sampling import sample_candidates
from pathfinder.domain.audit.scope import GeneTarget, paired_genome
from pathfinder.domain.audit.screen import (
    Candidate,
    audited_groups,
    pseudogene_candidates,
    screen_genomes,
)
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
)
from pathfinder.services.audit.checks import UnitFailure
from pathfinder.services.audit.progress import StageLane, not_read, plural
from pathfinder.services.audit.units import (
    NOT_READ,
    UNIT_FAILURES,
    Waits,
    failure_status,
    in_passes,
    tallied,
)

_ORTHOLOG_CHECKS = frozenset({"gene_length", "gene_split"})
_CALL_KEYS = "pseudogene_call:"


async def _rows(
    run: AuditRunRecord, screened: frozenset[str]
) -> tuple[dict[str, list[GeneRow]], list[GeneRow]]:
    if not _ORTHOLOG_CHECKS.intersection(run.scope.checks):
        return {}, []
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        audited: dict[str, list[GeneRow]] = {}
        for genome in run.scope.genomes:
            if genome not in screened:
                rows = await repo.collected_genome(run.id, genome)
                if rows:
                    audited[genome] = rows
        wanted = audited_groups(audited)
        if not wanted:
            return audited, []
        judging = [g for g in run.scope.genomes if g in screened]
        comparison = [
            row
            for organism in (*judging, *run.scope.comparison)
            for row in await repo.collected_genome(run.id, organism)
            if row.ortholog_group in wanted
        ]
    return audited, comparison


@dataclass(frozen=True, kw_only=True)
class _Calls:
    candidates: list[Candidate] = field(default_factory=list)
    genomes: frozenset[str] = frozenset()
    uncollected: str | None = None


async def _pseudogene_calls(
    run: AuditRunRecord, paired: frozenset[str], audited: dict[str, list[GeneRow]]
) -> _Calls:
    reference = run.scope.reference_genome
    unpaired = [g for g in run.scope.genomes if g not in paired]
    if reference is None or not unpaired:
        return _Calls()
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        held = {
            genome: audited[genome]
            if genome in audited
            else await repo.collected_genome(run.id, genome)
            for genome in {reference, *unpaired}
        }
    if not held[reference]:
        return _Calls(uncollected=reference)
    genomes = {genome: held[genome] for genome in unpaired}
    found = await asyncio.to_thread(
        pseudogene_candidates, reference, held[reference], genomes
    )
    screened = frozenset(g for g, rows in genomes.items() if rows) - {reference}
    return _Calls(candidates=found, genomes=screened)


@dataclass(frozen=True, kw_only=True)
class _TargetRead:
    genomes: dict[str, str] = field(default_factory=dict)
    unreached: str | None = None
    unread: bool = False


async def _target_rows(site_id: str, genes: list[str]) -> list[GeneRow] | UnitFailure:
    try:
        return await gene_rows(site_id, genes)
    except UNIT_FAILURES as exc:
        return UnitFailure(status=failure_status(exc), message=str(exc))


async def _counted(run_id: UUID, requests: int) -> None:
    async with async_session_factory() as session:
        await AuditRepository(session).count_requests(run_id, "screen", requests)
        await session.commit()


async def _noted(run_id: UUID, message: str) -> None:
    async with async_session_factory() as session:
        await AuditRepository(session).note_target_failure(run_id, message)
        await session.commit()


async def _read_targets(
    run: AuditRunRecord, targets: Sequence[GeneTarget], lane: StageLane, waits: Waits
) -> _TargetRead:
    genes = sorted({gene for target in targets for gene in target.genes})
    found: dict[str, str] = {}
    failures: list[str] = []

    async def attempt(_: UUID) -> bool:
        async with tallied(run.id, "screen") as tally:
            read = await _target_rows(run.site_id, genes)
        await _counted(run.id, tally.count)
        match read:
            case UnitFailure(status=status, message=message):
                failures.append(message)
                if status == "unreached":
                    await _noted(run.id, message)
                await lane.update(
                    done=0,
                    total=1,
                    message=f"{run.site_id}: gene targets {status} ({message})",
                )
                return status == "failed"
            case _:
                found.update({row.gene: row.organism for row in read})
                return True

    async def pausing(seconds: float, left: Sequence[UUID]) -> None:
        del left
        await lane.update(
            done=0,
            total=1,
            message=f"waiting {seconds:g} s for {run.site_id}, gene targets unanswered",
        )

    async def unread(left: Sequence[UUID]) -> None:
        del left
        await lane.update(
            done=0, total=1, message=not_read(len(targets), "gene target")
        )

    left = (
        await in_passes([run.id], attempt, waits, unread=unread, on_pause=pausing)
        if genes
        else []
    )
    missed = failures[-1] if failures else run.stages.target_failure
    return _TargetRead(
        genomes=found,
        unreached=(missed or NOT_READ) if left else None,
        unread=bool(left) and missed is None,
    )


@dataclass(frozen=True, kw_only=True)
class _Written:
    screened: frozenset[str]
    paired: frozenset[str]
    keys: frozenset[str]


async def _written(run: AuditRunRecord, named: frozenset[str]) -> _Written:
    async with async_session_factory() as session:
        keys = await AuditFindingRepository(session).finding_keys(run.id)
    found = [(genome, key) for genome, key in keys if key not in named]
    calls = [(genome, key.startswith(_CALL_KEYS)) for genome, key in found]
    return _Written(
        screened=frozenset(genome for genome, call in calls if not call),
        paired=frozenset(genome for genome, call in calls if call),
        keys=frozenset(key for _, key in keys),
    )


def _said(calls: _Calls) -> str:
    if calls.uncollected is None:
        return ""
    return f"; reference genome {calls.uncollected} not collected"


def _target_finding(target: GeneTarget, read: _TargetRead) -> NewFinding:
    if target.genome is not None:
        return NewFinding(
            genome=target.genome, target=target, sampled=True, status="screened"
        )
    if read.unreached is not None:
        return NewFinding(
            genome="",
            target=target,
            sampled=True,
            status="unread" if read.unread else "unreached",
            message=read.unreached,
        )
    return NewFinding(
        genome=read.genomes.get(target.genes[0], ""),
        paired_genome=paired_genome(target, read.genomes),
        target=target,
        sampled=True,
        status="screened",
    )


def _candidate_findings(
    candidates: Sequence[Candidate], chosen: frozenset[str]
) -> list[NewFinding]:
    return [
        NewFinding(
            genome=c.genome,
            target=c.target,
            sampled=c.target.key in chosen,
            status="screened" if c.target.key in chosen else "unsampled",
        )
        for c in candidates
    ]


async def _written_findings(run_id: UUID, findings: Sequence[NewFinding]) -> None:
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(run_id, findings)
        await session.commit()


async def run_screen_stage(run: AuditRunRecord, lane: StageLane, waits: Waits) -> None:
    named = frozenset(target.key for target in run.scope.targets)
    written = await _written(run, named)
    audited, comparison = await _rows(run, written.screened)
    found = await asyncio.to_thread(
        screen_genomes, run.scope.checks, audited, comparison
    )
    calls = await _pseudogene_calls(run, written.paired, audited)
    candidates = [c for c in (*found, *calls.candidates) if c.target.key not in named]
    chosen = sample_candidates(candidates, run.scope.confirm_limit, run.seed)
    await _written_findings(run.id, _candidate_findings(candidates, chosen))
    targets = [t for t in run.scope.targets if t.key not in written.keys]
    placing = [t for t in targets if t.genome is None]
    read = await _read_targets(run, placing, lane, waits)
    await _written_findings(run.id, [_target_finding(t, read) for t in targets])
    await lane.update(
        done=1,
        total=1,
        message=(
            f"{plural(len(candidates), 'candidate')} in "
            f"{plural(len({*audited, *calls.genomes}), 'genome')}, "
            f"{len(chosen)} sampled; {plural(len(targets), 'gene target')}"
            f"{_said(calls)}"
        ),
    )
