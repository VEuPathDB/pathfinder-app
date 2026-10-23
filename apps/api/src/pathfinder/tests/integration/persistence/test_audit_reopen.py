"""Reopening a run's unreached units, and sweeping its stopped ones, touch only that run."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.domain.audit.stages import STAGES
from pathfinder.persistence.repositories.audit import (
    STOPPED_MESSAGE,
    AuditRepository,
    CollectedGenome,
)
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.tests._support.audit import NF54, PIGA_INTACT, gene_row
from pathfinder.tests.integration.persistence._audit_runs import (
    UNREACHED,
    UnitState,
    new_run,
    unit_states,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

REFUSED = "plasmodb refused the request"
FINDINGS = ("SCREENED", "UNSAMPLED", "UNREACHED", "FAILED", "CAPPED", "CONFIRMED")
CONFIRMED = SettledFinding(
    status="confirmed", error_type="truncated_model", certainty="high"
)
CONFIRMATION = ConfirmationEvidence(
    confirmation=PseudogeneConfirmation(result=PIGA_INTACT)
)
BEFORE: dict[str, UnitState] = {
    "G pending": ("pending", 0, 0, None),
    "G unreached": ("unreached", 2, 1, UNREACHED),
    "G failed": ("failed", 1, 0, REFUSED),
    "G collected": ("collected", 1, 0, None),
    "gene_length:SCREENED": ("screened", 0, 0, None),
    "gene_length:UNSAMPLED": ("unsampled", 0, 0, None),
    "gene_length:UNREACHED": ("unreached", 2, 1, UNREACHED),
    "gene_length:FAILED": ("failed", 1, 0, REFUSED),
    "gene_length:CAPPED": ("failed", 3, 3, STOPPED_MESSAGE),
    "gene_length:CONFIRMED": ("confirmed", 1, 0, None),
    "gene_length:CONFIRMED/confirmation": ("stored", 0, 0, None),
    "gene_length:CONFIRMED/relatives": ("unreached", 2, 1, UNREACHED),
    "gene_length:FAILED/relatives": ("failed", 1, 0, REFUSED),
    "gene_length:FAILED/confirmation": ("pending", 1, 1, None),
}


async def _genomes(runs: AuditRepository, run_id: UUID) -> None:
    await runs.add_genomes(
        run_id,
        [
            (g, "audited")
            for g in ("G pending", "G unreached", "G failed", "G collected")
        ],
    )
    await runs.try_genome(run_id, "G unreached")
    await runs.sweep_genomes(run_id)
    settled = [
        CollectedGenome(organism="G unreached", status="unreached", message=UNREACHED),
        CollectedGenome(organism="G failed", status="failed", message=REFUSED),
        CollectedGenome(
            organism="G collected", status="collected", genes=[gene_row("A", NF54, 9)]
        ),
    ]
    for genome in settled:
        await runs.try_genome(run_id, genome.organism)
        await runs.save_genome(run_id, genome)


async def _findings(findings: AuditFindingRepository, run_id: UUID) -> None:
    await findings.add_findings(
        run_id,
        [
            NewFinding(
                genome=NF54,
                target=SingleGeneTarget(check="gene_length", genes=(name,)),
                sampled=name != "UNSAMPLED",
                status="unsampled" if name == "UNSAMPLED" else "screened",
            )
            for name in FINDINGS
        ],
    )
    _, _, unreached, failed, capped, confirmed = await findings.findings(
        run_id, FindingFilter()
    )
    await findings.try_finding(unreached.id)
    await findings.sweep_findings(run_id)
    for _ in range(3):
        await findings.try_finding(capped.id)
        await findings.sweep_findings(run_id)
    settled = [
        (unreached.id, SettledFinding(status="unreached", message=UNREACHED)),
        (failed.id, SettledFinding(status="failed", message=REFUSED)),
        (confirmed.id, CONFIRMED),
    ]
    for finding_id, settlement in settled:
        await findings.try_finding(finding_id)
        await findings.settle_finding(finding_id, settlement)
    await _evidence(findings, run_id, failed=failed.id, confirmed=confirmed.id)


async def _evidence(
    findings: AuditFindingRepository, run_id: UUID, *, failed: int, confirmed: int
) -> None:
    await findings.save_evidence(confirmed, CONFIRMATION, requests=0)
    await findings.try_evidence(confirmed, "relatives")
    await findings.sweep_evidence(run_id, "relatives")
    await findings.try_evidence(confirmed, "relatives")
    await findings.fail_evidence(
        confirmed, "relatives", status="unreached", message=UNREACHED, requests=0
    )
    await findings.try_evidence(failed, "relatives")
    await findings.fail_evidence(
        failed, "relatives", status="failed", message=REFUSED, requests=0
    )
    await findings.try_evidence(failed, "confirmation")
    await findings.sweep_evidence(run_id, "confirmation")


async def _finished_run_with_every_status(
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    user_id, run_id = await new_run(session_maker)
    async with session_maker() as session:
        runs = AuditRepository(session)
        await _genomes(runs, run_id)
        await _findings(AuditFindingRepository(session), run_id)
        for stage in STAGES:
            await runs.finish_stage(run_id, stage)
        await runs.set_status(run_id, "finished")
        await session.commit()
    return user_id, run_id


async def test_a_reopen_reaches_the_first_stage_and_only_the_runs_unreached_units(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_a, run_a = await _finished_run_with_every_status(session_maker)
    user_b, run_b = await _finished_run_with_every_status(session_maker)
    async with session_maker() as session:
        runs = AuditRepository(session)
        assert await unit_states(session, run_a) == BEFORE
        assert await runs.reopen_unreached(run_a) == "collect"
        assert await runs.reopen_unreached(run_a) is None
        await session.commit()
    async with session_maker() as session:
        runs = AuditRepository(session)
        reopened, untouched = (
            await runs.run(run_a, user_id=user_a),
            await runs.run(run_b, user_id=user_b),
        )
        after_a, after_b = (
            await unit_states(session, run_a),
            await unit_states(session, run_b),
        )
    assert reopened is not None
    assert untouched is not None
    assert (reopened.status, reopened.finished_at, reopened.stages.unfinished) == (
        "running",
        None,
        STAGES,
    )
    assert (untouched.status, untouched.stages.unfinished) == ("finished", ())
    assert after_b == BEFORE
    assert after_a == BEFORE | {
        "G unreached": ("pending", 2, 1, None),
        "gene_length:UNREACHED": ("screened", 2, 1, None),
        "gene_length:CONFIRMED/relatives": ("pending", 2, 1, None),
    }


async def test_unreached_evidence_alone_reopens_the_tie_break(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, run_id = await new_run(session_maker)
    async with session_maker() as session:
        runs, findings = AuditRepository(session), AuditFindingRepository(session)
        target = SingleGeneTarget(check="gene_length", genes=("CONFIRMED",))
        await findings.add_findings(
            run_id,
            [NewFinding(genome=NF54, target=target, sampled=True, status="screened")],
        )
        (finding,) = await findings.findings(run_id, FindingFilter())
        await findings.try_finding(finding.id)
        await findings.settle_finding(finding.id, CONFIRMED)
        await findings.try_evidence(finding.id, "relatives")
        await findings.fail_evidence(
            finding.id, "relatives", status="unreached", message=UNREACHED, requests=1
        )
        for stage in STAGES:
            await runs.finish_stage(run_id, stage)
        await runs.set_status(run_id, "finished")
        assert await runs.reopen_unreached(run_id) == "tie_break"
        await session.commit()
    async with session_maker() as session:
        run = await AuditRepository(session).run(run_id, user_id=user_id)
        states = await unit_states(session, run_id)
    assert run is not None
    assert (run.status, run.stages.unfinished) == ("running", ("tie_break",))
    assert states == {
        "gene_length:CONFIRMED": ("confirmed", 1, 0, None),
        "gene_length:CONFIRMED/relatives": ("pending", 1, 0, None),
    }


async def test_a_sweep_leaves_another_runs_trying_units_alone(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, run_a = await new_run(session_maker)
    _, run_b = await new_run(session_maker)
    target = SingleGeneTarget(check="gene_length", genes=("TRYING",))
    async with session_maker() as session:
        runs, findings = AuditRepository(session), AuditFindingRepository(session)
        for run_id in (run_a, run_b):
            await runs.add_genomes(run_id, [(NF54, "audited")])
            await runs.try_genome(run_id, NF54)
            await findings.add_findings(
                run_id,
                [
                    NewFinding(
                        genome=NF54, target=target, sampled=True, status="screened"
                    )
                ],
            )
            (finding,) = await findings.findings(run_id, FindingFilter())
            await findings.try_finding(finding.id)
            await findings.try_evidence(finding.id, "relatives")
        await runs.sweep_genomes(run_a)
        await findings.sweep_findings(run_a)
        await findings.sweep_evidence(run_a, "relatives")
        await session.commit()
    async with session_maker() as session:
        swept, untouched = (
            await unit_states(session, run_a),
            await unit_states(session, run_b),
        )
    assert swept == {
        NF54: ("pending", 1, 1, None),
        "gene_length:TRYING": ("screened", 1, 1, None),
        "gene_length:TRYING/relatives": ("pending", 1, 1, None),
    }
    assert untouched == {
        NF54: ("trying", 1, 0, None),
        "gene_length:TRYING": ("trying", 1, 0, None),
        "gene_length:TRYING/relatives": ("trying", 1, 0, None),
    }
