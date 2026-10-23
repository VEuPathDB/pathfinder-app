"""The read views of a stored audit run, built from storage alone."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb_mcp.audit import GenomePriority

from pathfinder.domain.audit.findings import (
    FindingTally,
)
from pathfinder.domain.audit.rates import (
    GenomeRate,
    TargetFinding,
    TargetReport,
    genome_rates,
    target_report,
)
from pathfinder.domain.audit.run_state import (
    EvidenceTally,
    LeftUnits,
    RunAction,
    RunPhase,
    left_units,
    reviews_running,
    run_action,
    run_phase,
)
from pathfinder.domain.audit.scope import (
    AuditScope,
    CheckName,
    GenomeRole,
    GenomeStatus,
)
from pathfinder.domain.audit.stages import RunHalt, RunStages, RunStatus, StageName
from pathfinder.domain.audit.verdicts import ReviewProgress, Synthesis
from pathfinder.persistence.models import AuditFindingRecord, AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.persistence.repositories.audit_tallies import AuditTallyRepository
from pathfinder.services.audit.runs import readable_run


class AuditRunSummary(CamelModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    site_id: str
    conversation_id: UUID | None
    release: str | None
    status: RunStatus
    phase: RunPhase
    deadline_at: datetime | None
    genomes: list[str]
    checks: list[CheckName]
    targets: int
    created_at: datetime
    finished_at: datetime | None


class GenomeView(CamelModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    organism: str
    role: GenomeRole
    status: GenomeStatus
    gene_count: int
    requests: int
    attempts: int
    stopped: int
    message: str | None
    priority: GenomePriority | None
    reference_strain: bool | None


class AuditRunView(CamelModel):
    model_config = ConfigDict(frozen=True)

    run: AuditRunSummary
    scope: AuditScope
    stages: RunStages
    requests: int
    store_reads: int
    unfinished: list[StageName]
    genomes: list[GenomeView]
    counts: list[FindingTally]
    rates: list[GenomeRate]
    targets: TargetReport
    review: ReviewProgress | None
    synthesis: Synthesis | None
    reviewed: int
    action: RunAction | None
    reviews_running: bool
    halt: RunHalt | None
    left: LeftUnits
    evidence: list[EvidenceTally]


def _summary(run: AuditRunRecord) -> AuditRunSummary:
    return AuditRunSummary(
        id=run.id,
        site_id=run.site_id,
        conversation_id=run.conversation_id,
        release=run.release,
        status=run.status,
        phase=run_phase(
            run.status,
            halted=run.stages.halted is not None,
            deadline_at=run.deadline_at,
        ),
        deadline_at=run.deadline_at,
        genomes=list(run.scope.genomes),
        checks=sorted({*run.scope.checks, *(t.check for t in run.scope.targets)}),
        targets=len(run.scope.targets),
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def _target(finding: AuditFindingRecord) -> TargetFinding:
    judged = (finding.screened_genome, finding.paired_genome or "")
    return TargetFinding(
        check=finding.target.check,
        status=finding.status,
        error_type=finding.error_type,
        judged=finding.judged,
        model_genome=finding.genome,
        judged_genomes=tuple(dict.fromkeys(judged)),
    )


async def list_runs(user_id: UUID) -> list[AuditRunSummary]:
    async with async_session_factory() as session:
        runs = await AuditRepository(session).runs(user_id=user_id)
    return [_summary(run) for run in runs]


async def run_view(run_id: UUID, user_id: UUID) -> AuditRunView:
    run = await readable_run(run_id, user_id)
    keys = tuple(target.key for target in run.scope.targets)
    async with async_session_factory() as session:
        genomes = await AuditRepository(session).genome_states(run_id)
        tallies = AuditTallyRepository(session)
        tally = await tallies.tally(run_id)
        sample = await tallies.sample_tally(run_id, keys)
        targets = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(keys=keys)
        )
        evidence = await tallies.evidence_tally(run_id)
        reviewed = await AuditReviewRepository(session).reviewed_count(run_id)
    summary = _summary(run)
    left = left_units((genome.status for genome in genomes), tally, evidence)
    running = reviews_running(summary.phase, run.review)
    return AuditRunView(
        run=summary,
        scope=run.scope,
        stages=run.stages,
        requests=run.stages.requests,
        store_reads=run.stages.store_reads,
        unfinished=list(run.stages.unfinished),
        genomes=[GenomeView.model_validate(genome) for genome in genomes],
        counts=tally,
        rates=genome_rates(sample),
        targets=target_report(_target(finding) for finding in targets),
        review=run.review,
        synthesis=run.synthesis,
        reviewed=reviewed,
        action=run_action(summary.phase, left, reviews_running=running),
        reviews_running=running,
        halt=run.stages.halt_reason,
        left=left,
        evidence=evidence,
    )
