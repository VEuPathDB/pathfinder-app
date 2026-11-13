"""One audit run's findings, filtered and paged, and one finding with its evidence, read from storage."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field

from strategist.domain.audit.check_facts import evidence_facts
from strategist.domain.audit.confirmations import Confirmation, FindingVerdict
from strategist.domain.audit.facts import EvidenceFacts
from strategist.domain.audit.findings import (
    Certainty,
    ConfirmationEvidence,
    ErrorType,
    EvidenceKind,
    EvidencePayload,
    EvidenceStatus,
    FindingStatus,
)
from strategist.domain.audit.genes import evidence_genes, named_genes
from strategist.domain.audit.models import FindingModels, finding_models
from strategist.domain.audit.rates import Weighing
from strategist.domain.audit.scope import CheckName, GeneTarget
from strategist.domain.audit.verdicts import FindingReview
from strategist.domain.audit.words import (
    CHECK_TITLES,
    ERROR_TYPE_TITLES,
    rejected_sentence,
    verdict_sentence,
)
from strategist.domain.statistic_facts import Identifier, Sentence
from strategist.persistence.models import (
    AuditEvidenceRecord,
    AuditFindingRecord,
    AuditRunRecord,
)
from strategist.persistence.repositories.audit_finding_filter import FindingFilter
from strategist.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from strategist.platform.errors import NotFoundError
from strategist.services.audit.review_views import (
    ReviewLine,
    ReviewText,
    review_line,
    review_text,
)
from strategist.services.audit.runs import readable_run
from strategist.services.record_pages import record_page_url

MAX_PAGE = 200
DEFAULT_PAGE = 50
MAX_ROW_ID = 2**63 - 1
_FACT_ORDER: tuple[EvidenceKind, ...] = ("confirmation", "relatives", "gene_evidence")


class GeneLink(CamelModel):
    model_config = ConfigDict(frozen=True)

    gene: str
    url: str


def _links(site_id: str, genes: Iterable[str]) -> list[GeneLink]:
    return [
        GeneLink(gene=gene, url=record_page_url(site_id, "gene", gene))
        for gene in genes
    ]


class FindingView(CamelModel):
    model_config = ConfigDict(frozen=True)

    id: Identifier
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
    message: Sentence | None
    reviewed: bool
    verdict: FindingVerdict | None
    from_target: bool
    review_line: ReviewLine | None
    genes: list[GeneLink]

    @computed
    def check(self) -> CheckName:
        return self.target.check

    @computed
    def verdict_text(self) -> Sentence | None:
        return (
            None if self.verdict is None else verdict_sentence(self.check, self.verdict)
        )

    @computed
    def check_title(self) -> str:
        return CHECK_TITLES[self.check]

    @computed
    def error_title(self) -> str | None:
        return None if self.error_type is None else ERROR_TYPE_TITLES[self.error_type]

    @property
    def _rejected(self) -> bool:
        return (
            self.review_line is not None
            and self.review_line.verdict == "no_error"
            and self.error_type is not None
        )

    @computed
    def effective_error_type(self) -> ErrorType | None:
        if self._rejected:
            return None
        reviewed = None if self.review_line is None else self.review_line.error_type
        return reviewed or self.error_type

    @computed
    def effective_error_title(self) -> str | None:
        kind = self.effective_error_type
        return None if kind is None else ERROR_TYPE_TITLES[kind]

    @computed
    def effective_certainty(self) -> Certainty | None:
        if self._rejected:
            return None
        reviewed = None if self.review_line is None else self.review_line.certainty
        return reviewed or self.certainty

    @computed
    def rejected_text(self) -> Sentence | None:
        if not self._rejected or self.error_title is None:
            return None
        return rejected_sentence(self.error_title)


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
    message: Sentence | None


class FindingDetail(CamelModel):
    model_config = ConfigDict(frozen=True)

    site_id: str
    finding: FindingView
    evidence: list[EvidenceView]
    facts: list[EvidenceFacts]
    review: FindingReview | None
    review_text: ReviewText | None
    genes: list[GeneLink]
    models: FindingModels | None


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
    site_id: str,
    confirmation: Confirmation | None,
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
        verdict=None if confirmation is None else confirmation.verdict,
        from_target=from_target,
        review_line=None if record.review is None else review_line(record.review),
        genes=_links(site_id, named_genes(record.target, confirmation)),
    )


def _confirmations(
    evidence: Iterable[AuditEvidenceRecord],
) -> dict[int, Confirmation]:
    found: dict[int, Confirmation] = {}
    for record in evidence:
        match record.payload:
            case ConfirmationEvidence(confirmation=confirmation):
                found[record.finding_id] = confirmation
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
    site_id: str,
    found: Iterable[AuditFindingRecord],
    evidence: Iterable[AuditEvidenceRecord],
    target_keys: Collection[str],
) -> list[FindingView]:
    confirmations = _confirmations(evidence)
    return [
        _view(
            record,
            site_id=site_id,
            confirmation=confirmations.get(record.id),
            from_target=record.target.key in target_keys,
        )
        for record in found
    ]


@dataclass(frozen=True)
class StoredFinding:
    finding: FindingView
    evidence: tuple[AuditEvidenceRecord, ...]
    review: FindingReview | None


async def stored_findings(
    run: AuditRunRecord, *, offset: int, limit: int
) -> list[StoredFinding]:
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        found = await repo.findings(run.id, FindingFilter(), offset=offset, limit=limit)
        evidence = await repo.evidence(run.id, [record.id for record in found])
    held: defaultdict[int, list[AuditEvidenceRecord]] = defaultdict(list)
    for record in evidence:
        held[record.finding_id].append(record)
    views = _views(run.site_id, found, evidence, {t.key for t in run.scope.targets})
    return [
        StoredFinding(finding=view, evidence=tuple(held[view.id]), review=record.review)
        for view, record in zip(views, found, strict=True)
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
        findings=_views(run.site_id, found, evidence, set(target_keys)),
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
    (finding,) = _views(
        run.site_id, [found], evidence, {t.key for t in run.scope.targets}
    )
    payloads = [record.payload for record in evidence if record.payload is not None]
    named = [link.gene for link in finding.genes]
    confirmation = _confirmations(evidence).get(finding_id)
    return FindingDetail(
        site_id=run.site_id,
        finding=finding,
        evidence=[EvidenceView.model_validate(record) for record in evidence],
        facts=stored_facts(evidence),
        review=review,
        review_text=None if review is None else review_text(review),
        genes=_links(run.site_id, dict.fromkeys([*named, *evidence_genes(payloads)])),
        models=None if confirmation is None else finding_models(confirmation),
    )
