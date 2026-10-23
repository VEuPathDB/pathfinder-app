"""The read views of a stored audit run, built from storage alone."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field
from veupathdb_mcp.audit import GenomePriority

from pathfinder.domain.audit.findings import (
    Certainty,
    ErrorType,
    EvidenceKind,
    EvidencePayload,
    EvidenceStatus,
    FindingStatus,
    FindingTally,
)
from pathfinder.domain.audit.rates import (
    GenomeRate,
    TargetFinding,
    TargetReport,
    Weighing,
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
    GeneTarget,
    GenomeRole,
    GenomeStatus,
)
from pathfinder.domain.audit.stages import RunHalt, RunStages, RunStatus, StageName
from pathfinder.domain.audit.verdicts import FindingReview, ReviewProgress, Synthesis
from pathfinder.persistence.models import AuditFindingRecord, AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.persistence.repositories.audit_tallies import AuditTallyRepository
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.audit.runs import readable_run

MAX_PAGE = 200
DEFAULT_PAGE = 50
MAX_ROW_ID = 2**63 - 1


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


class FindingView(CamelModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    genome: str
    screened_genome: str
    paired_genome: str | None
    target: GeneTarget
    sampled: bool
    status: FindingStatus
    error_type: ErrorType | None
    certainty: Certainty | None
    judged: bool
    impact: float | None
    weighing: Weighing | None
    requests: int
    attempts: int
    stopped: int
    message: str | None
    reviewed: bool

    @computed
    def check(self) -> CheckName:
        return self.target.check


class FindingPage(CamelModel):
    model_config = ConfigDict(frozen=True)

    site_id: str
    total: int
    offset: int
    findings: list[FindingView]


class EvidenceView(CamelModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    kind: EvidenceKind
    status: EvidenceStatus
    payload: EvidencePayload | None
    requests: int
    attempts: int
    stopped: int
    message: str | None


class FindingDetail(CamelModel):
    model_config = ConfigDict(frozen=True)

    site_id: str
    finding: FindingView
    evidence: list[EvidenceView]
    review: FindingReview | None


class FindingQuery(CamelModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_by_name=False)

    check: CheckName | None = None
    genome: str | None = None
    screened_genome: str | None = None
    sampled: bool | None = None
    status: FindingStatus | None = None
    error_type: ErrorType | None = None
    offset: int = Field(default=0, ge=0, le=MAX_ROW_ID)
    limit: int = Field(default=DEFAULT_PAGE, ge=1, le=MAX_PAGE)

    @property
    def where(self) -> FindingFilter:
        return FindingFilter(
            checks=() if self.check is None else (self.check,),
            statuses=() if self.status is None else (self.status,),
            error_types=() if self.error_type is None else (self.error_type,),
            genome=self.genome,
            screened_genome=self.screened_genome,
            sampled=self.sampled,
        )


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


async def finding_page(run_id: UUID, user_id: UUID, query: FindingQuery) -> FindingPage:
    run = await readable_run(run_id, user_id)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        total = await repo.count_findings(run_id, query.where)
        found = await repo.findings(
            run_id,
            query.where,
            offset=query.offset,
            limit=query.limit,
            by_impact=True,
        )
    return FindingPage(
        site_id=run.site_id,
        total=total,
        offset=query.offset,
        findings=[FindingView.model_validate(finding) for finding in found],
    )


async def finding_detail(run_id: UUID, finding_id: int, user_id: UUID) -> FindingDetail:
    run = await readable_run(run_id, user_id)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        found = await repo.finding(run_id, finding_id)
        if found is None:
            raise NotFoundError(
                title="Audit finding not found",
                detail=f"no finding {finding_id} in run {run_id}",
            )
        evidence = await repo.evidence(run_id, [finding_id])
        review = await AuditReviewRepository(session).review_of(finding_id)
    return FindingDetail(
        site_id=run.site_id,
        finding=FindingView.model_validate(found),
        evidence=[EvidenceView.model_validate(record) for record in evidence],
        review=review,
    )
