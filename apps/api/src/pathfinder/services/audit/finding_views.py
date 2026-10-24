"""One audit run's findings, filtered and paged, and one finding with its evidence, read from storage."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field

from pathfinder.domain.audit.check_facts import evidence_facts
from pathfinder.domain.audit.confirmations import FindingVerdict
from pathfinder.domain.audit.facts import EvidenceFacts
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
from pathfinder.domain.audit.words import (
    CHECK_TITLES,
    ERROR_TYPE_TITLES,
    verdict_sentence,
)
from pathfinder.persistence.models import AuditEvidenceRecord, AuditFindingRecord
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.audit.review_views import (
    ReviewLine,
    ReviewText,
    review_line,
    review_text,
)
from pathfinder.services.audit.runs import readable_run

MAX_PAGE = 200
DEFAULT_PAGE = 50
MAX_ROW_ID = 2**63 - 1
_FACT_ORDER: tuple[EvidenceKind, ...] = ("confirmation", "relatives", "gene_evidence")


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
    review_line: ReviewLine | None

    @computed
    def check(self) -> CheckName:
        return self.target.check

    @computed
    def verdict_text(self) -> str | None:
        return (
            None if self.verdict is None else verdict_sentence(self.check, self.verdict)
        )

    @computed
    def check_title(self) -> str:
        return CHECK_TITLES[self.check]

    @computed
    def error_title(self) -> str | None:
        return None if self.error_type is None else ERROR_TYPE_TITLES[self.error_type]


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
    facts: list[EvidenceFacts]
    review: FindingReview | None
    review_text: ReviewText | None


class FindingQuery(CamelModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_by_name=False)

    check: CheckName | None = None
    genome: str | None = None
    screened_genome: str | None = None
    sampled: bool | None = None
    status: FindingStatus | None = None
    error_type: ErrorType | None = None
    certainty: Certainty | None = None
    target: bool | None = None
    offset: int = Field(default=0, ge=0, le=MAX_ROW_ID)
    limit: int = Field(default=DEFAULT_PAGE, ge=1, le=MAX_PAGE)

    def where(self, target_keys: tuple[str, ...]) -> FindingFilter:
        return FindingFilter(
            checks=() if self.check is None else (self.check,),
            statuses=() if self.status is None else (self.status,),
            error_types=() if self.error_type is None else (self.error_type,),
            certainties=() if self.certainty is None else (self.certainty,),
            genome=self.genome,
            screened_genome=self.screened_genome,
            sampled=self.sampled,
            keys=target_keys if self.target is True else None,
            excluded_keys=target_keys if self.target is False else (),
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
        review_line=None if record.review is None else review_line(record.review),
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


def stored_facts(evidence: Iterable[AuditEvidenceRecord]) -> list[EvidenceFacts]:
    stored = [
        evidence_facts(record.payload)
        for record in evidence
        if record.payload is not None
    ]
    return sorted(stored, key=lambda group: _FACT_ORDER.index(group.kind))


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
    target_keys = tuple(t.key for t in run.scope.targets)
    where = query.where(target_keys)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        total = await repo.count_findings(run_id, where)
        found = await repo.findings(
            run_id,
            where,
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
        findings=_views(found, evidence, set(target_keys)),
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
    review = found.review
    (finding,) = _views([found], evidence, {t.key for t in run.scope.targets})
    return FindingDetail(
        site_id=run.site_id,
        finding=finding,
        evidence=[EvidenceView.model_validate(record) for record in evidence],
        facts=stored_facts(evidence),
        review=review,
        review_text=None if review is None else review_text(review),
    )
