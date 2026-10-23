"""One audit run's findings, filtered and paged, and one finding with its evidence, read from storage."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field

from pathfinder.domain.audit.confirmations import FindingVerdict
from pathfinder.domain.audit.findings import (
    Certainty,
    ConfirmationEvidence,
    ErrorType,
    EvidenceKind,
    EvidencePayload,
    EvidenceStatus,
    FindingStatus,
)
from pathfinder.domain.audit.rates import Weighing
from pathfinder.domain.audit.scope import CheckName, GeneTarget
from pathfinder.domain.audit.verdicts import FindingReview
from pathfinder.persistence.models import AuditEvidenceRecord, AuditFindingRecord
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.audit.runs import readable_run

MAX_PAGE = 200
DEFAULT_PAGE = 50
MAX_ROW_ID = 2**63 - 1


class FindingView(CamelModel):
    model_config = ConfigDict(frozen=True)

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
    verdict: FindingVerdict | None
    from_target: bool

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


def _view(
    record: AuditFindingRecord,
    *,
    verdict: FindingVerdict | None,
    from_target: bool,
) -> FindingView:
    return FindingView(
        id=record.id,
        genome=record.genome,
        screened_genome=record.screened_genome,
        paired_genome=record.paired_genome,
        target=record.target,
        sampled=record.sampled,
        status=record.status,
        error_type=record.error_type,
        certainty=record.certainty,
        judged=record.judged,
        impact=record.impact,
        weighing=record.weighing,
        requests=record.requests,
        attempts=record.attempts,
        stopped=record.stopped,
        message=record.message,
        reviewed=record.reviewed,
        verdict=verdict,
        from_target=from_target,
    )


def _verdicts(evidence: Iterable[AuditEvidenceRecord]) -> dict[int, FindingVerdict]:
    found: dict[int, FindingVerdict] = {}
    for record in evidence:
        match record.payload:
            case ConfirmationEvidence(confirmation=confirmation):
                found[record.finding_id] = confirmation.verdict
            case _:
                pass
    return found


def _views(
    found: Iterable[AuditFindingRecord],
    evidence: Iterable[AuditEvidenceRecord],
    target_keys: Collection[str],
) -> list[FindingView]:
    verdicts = _verdicts(evidence)
    return [
        _view(
            record,
            verdict=verdicts.get(record.id),
            from_target=record.target.key in target_keys,
        )
        for record in found
    ]


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
        evidence = await repo.evidence(
            run_id, [record.id for record in found], kinds=("confirmation",)
        )
    return FindingPage(
        site_id=run.site_id,
        total=total,
        offset=query.offset,
        findings=_views(found, evidence, {t.key for t in run.scope.targets}),
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
    (finding,) = _views([found], evidence, {t.key for t in run.scope.targets})
    return FindingDetail(
        site_id=run.site_id,
        finding=finding,
        evidence=[EvidenceView.model_validate(record) for record in evidence],
        review=review,
    )
