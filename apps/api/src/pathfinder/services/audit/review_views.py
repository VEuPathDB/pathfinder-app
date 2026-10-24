from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.audit.findings import Certainty, ErrorType
from pathfinder.domain.audit.verdicts import (
    ErrorTypeSection,
    FindingReview,
    LiteratureStatus,
    ReviewAgreement,
    ReviewProgress,
    ReviewStatus,
    Synthesis,
    VerdictKind,
    review_agreement,
)
from pathfinder.domain.audit.words import (
    ERROR_TYPE_DESCRIPTIONS,
    ERROR_TYPE_TITLES,
    LITERATURE_SENTENCES,
    REVIEW_STATUS_SENTENCES,
    VERDICT_KIND_SENTENCES,
    agreement_sentence,
    paper_sentence,
)
from pathfinder.domain.statistic_facts import Sentence, Share
from pathfinder.persistence.models import AuditFindingRecord
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.persistence.repositories.audit_tallies import AuditTallyRepository

SECOND_REVIEW = "A second, independent review"
_CERTAINTY_RANK: dict[Certainty, int] = {"low": 0, "medium": 1, "high": 2}


class ReviewLine(CamelModel):
    model_config = ConfigDict(frozen=True)

    verdict: VerdictKind
    verdict_text: Sentence
    second_verdict: VerdictKind | None
    impact: float | None
    impact_reason: Sentence | None
    literature: LiteratureStatus
    literature_text: Sentence


class ReviewText(CamelModel):
    model_config = ConfigDict(frozen=True)

    verdict_text: Sentence
    literature_text: Sentence
    paper_text: Sentence
    second_text: Sentence | None


class AgreementView(CamelModel):
    model_config = ConfigDict(frozen=True)

    sampled: int
    agreed: int
    share: Share | None
    text: Sentence


class FindingLine(CamelModel):
    model_config = ConfigDict(frozen=True)

    id: int
    genes: list[str]
    genome: str
    error_type: ErrorType | None
    error_title: str | None
    certainty: Certainty | None
    impact: float | None
    reviewed_impact: float | None


class ErrorTypeView(CamelModel):
    model_config = ConfigDict(frozen=True)

    error_type: ErrorType
    title: str
    description: Sentence
    count: int = Field(ge=0)
    genomes: list[str]
    certainty: Certainty
    cause: Sentence | None
    confirmed_by: Sentence | None
    reviewed: list[FindingLine]


class ReviewState(CamelModel):
    model_config = ConfigDict(frozen=True)

    status: ReviewStatus
    text: Sentence
    done: int
    total: int
    message: Sentence


def review_line(review: FindingReview) -> ReviewLine:
    verdict = review.verdict.verdict
    return ReviewLine(
        verdict=verdict,
        verdict_text=VERDICT_KIND_SENTENCES[verdict],
        second_verdict=review.second_verdict,
        impact=review.impact,
        impact_reason=review.impact_reason,
        literature=review.already_known,
        literature_text=LITERATURE_SENTENCES[review.already_known],
    )


def review_text(review: FindingReview) -> ReviewText:
    second = review.second_verdict
    return ReviewText(
        verdict_text=VERDICT_KIND_SENTENCES[review.verdict.verdict],
        literature_text=LITERATURE_SENTENCES[review.already_known],
        paper_text=paper_sentence(depends=review.paper_depends),
        second_text=None
        if second is None
        else f"{SECOND_REVIEW}: {VERDICT_KIND_SENTENCES[second]}",
    )


def agreement_view(agreement: ReviewAgreement) -> AgreementView:
    return AgreementView(
        sampled=agreement.sampled,
        agreed=agreement.agreed,
        share=agreement.share,
        text=agreement_sentence(agreement),
    )


def review_state(progress: ReviewProgress) -> ReviewState:
    return ReviewState(
        status=progress.status,
        text=REVIEW_STATUS_SENTENCES[progress.status],
        done=progress.done,
        total=progress.total,
        message=progress.message,
    )


class _Named(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    error_type: ErrorType
    certainty: Certainty


def _kept_as(review: FindingReview | None) -> _Named | None:
    if review is None or review.verdict.verdict != "error":
        return None
    return _Named.model_validate(review.verdict)


def finding_line(record: AuditFindingRecord) -> FindingLine:
    review = record.review
    kept = _kept_as(review)
    error_type = record.error_type if kept is None else kept.error_type
    return FindingLine(
        id=record.id,
        genes=list(record.target.genes),
        genome=record.genome,
        error_type=error_type,
        error_title=None if error_type is None else ERROR_TYPE_TITLES[error_type],
        certainty=record.certainty if kept is None else kept.certainty,
        impact=record.impact,
        reviewed_impact=None if review is None else review.impact,
    )


def finding_lines(records: Iterable[AuditFindingRecord]) -> dict[int, FindingLine]:
    return {record.id: finding_line(record) for record in records}


def error_type_views(
    tally: Iterable[tuple[ErrorType, str, Certainty, int]],
    synthesis: Synthesis | None,
    lines: Mapping[int, FindingLine],
) -> list[ErrorTypeView]:
    counts: Counter[ErrorType] = Counter()
    genomes: defaultdict[ErrorType, dict[str, None]] = defaultdict(dict)
    certainties: defaultdict[ErrorType, list[Certainty]] = defaultdict(list)
    for error_type, genome, certainty, count in tally:
        counts[error_type] += count
        genomes[error_type][genome] = None
        certainties[error_type].append(certainty)
    sections = (
        {} if synthesis is None else {s.error_type: s for s in synthesis.sections}
    )
    return [
        _error_type_view(
            error_type,
            count=counts[error_type],
            genomes=list(genomes[error_type]),
            certainty=max(certainties[error_type], key=_CERTAINTY_RANK.__getitem__),
            section=sections.get(error_type),
            lines=lines,
        )
        for error_type in ERROR_TYPE_TITLES
        if error_type in counts
    ]


def _error_type_view(
    error_type: ErrorType,
    *,
    count: int,
    genomes: list[str],
    certainty: Certainty,
    section: ErrorTypeSection | None,
    lines: Mapping[int, FindingLine],
) -> ErrorTypeView:
    return ErrorTypeView(
        error_type=error_type,
        title=ERROR_TYPE_TITLES[error_type],
        description=ERROR_TYPE_DESCRIPTIONS[error_type],
        count=count,
        genomes=genomes,
        certainty=certainty,
        cause=None if section is None else section.cause,
        confirmed_by=None if section is None else section.confirmed_by,
        reviewed=[] if section is None else [lines[f] for f in section.finding_ids],
    )


class ReviewReport(CamelModel):
    model_config = ConfigDict(frozen=True)

    error_types: list[ErrorTypeView]
    headline: list[FindingLine]
    agreement: AgreementView | None


def _named(synthesis: Synthesis) -> tuple[int, ...]:
    sections = (f for section in synthesis.sections for f in section.finding_ids)
    return tuple(dict.fromkeys([*sections, *synthesis.headline]))


async def review_report(
    session: AsyncSession, run_id: UUID, synthesis: Synthesis | None
) -> ReviewReport:
    tally = await AuditTallyRepository(session).error_type_tally(run_id)
    reviews = AuditReviewRepository(session)
    if synthesis is None:
        stored = [
            r.review for r in await reviews.of_run(run_id) if r.review is not None
        ]
        return ReviewReport(
            error_types=error_type_views(tally, None, {}),
            headline=[],
            agreement=agreement_view(review_agreement(stored)) if stored else None,
        )
    ids = _named(synthesis)
    found = await AuditFindingRepository(session).findings(
        run_id, FindingFilter(ids=ids)
    )
    lines = finding_lines(found)
    return ReviewReport(
        error_types=error_type_views(tally, synthesis, lines),
        headline=[lines[f] for f in synthesis.headline],
        agreement=agreement_view(synthesis.agreement),
    )
