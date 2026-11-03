"""One audit run's findings as CSV rows a curator reads in a spreadsheet, in the words of the report page."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator, Sequence

from pathfinder.domain.audit.verdicts import FindingReview
from pathfinder.domain.audit.words import (
    EVIDENCE_KIND_TITLES,
    EVIDENCE_STATUS_SENTENCES,
    LITERATURE_SENTENCES,
    UNCHECKED_SENTENCES,
    VERDICT_KIND_SENTENCES,
)
from pathfinder.persistence.models import AuditEvidenceRecord, AuditRunRecord
from pathfinder.services.audit.finding_views import (
    MAX_PAGE,
    FindingView,
    stored_facts,
    stored_findings,
)

HEADER = [
    "Genome",
    "Gene IDs",
    "Check",
    "Error",
    "Verdict",
    "Impact",
    "Review",
    "Second review",
    "Cause",
    "Literature",
    "Impact after review",
    "Fix",
    "Evidence",
    "Gene pages",
]
EXPORT_PAGE = MAX_PAGE
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(text: str) -> str:
    return f"'{text}" if text.startswith(_FORMULA) else text


def _evidence_text(evidence: Sequence[AuditEvidenceRecord]) -> str:
    facts = [
        f"{fact.label}: {fact.value}"
        for group in stored_facts(evidence)
        for fact in group.facts
    ]
    left = [
        f"{EVIDENCE_KIND_TITLES[record.kind]}: {EVIDENCE_STATUS_SENTENCES[record.status]}"
        for record in evidence
        if record.payload is None
    ]
    return "; ".join([*facts, *left])


def _number(value: float | None) -> str:
    return "" if value is None else str(value)


def _review_cells(review: FindingReview | None) -> list[str]:
    if review is None:
        return ["Not reviewed", "", "", "", "", ""]
    second = review.second_verdict
    return [
        VERDICT_KIND_SENTENCES[review.verdict.verdict],
        "" if second is None else VERDICT_KIND_SENTENCES[second],
        review.verdict.cause,
        "; ".join([LITERATURE_SENTENCES[review.already_known], *review.known_from]),
        _number(review.impact),
        review.card_text,
    ]


def finding_row(
    finding: FindingView,
    evidence: Sequence[AuditEvidenceRecord],
    review: FindingReview | None,
) -> list[str]:
    cells = [
        finding.genome,
        "; ".join(link.gene for link in finding.genes),
        finding.check_title,
        finding.error_title or "",
        finding.verdict_text or UNCHECKED_SENTENCES[finding.status],
        _number(finding.impact),
        *_review_cells(review),
        _evidence_text(evidence),
        "; ".join(link.url for link in finding.genes),
    ]
    return [safe_cell(cell) for cell in cells]


def _line(cells: list[str]) -> str:
    out = io.StringIO()
    csv.writer(out).writerow(cells)
    return out.getvalue()


async def finding_lines(run: AuditRunRecord) -> AsyncIterator[str]:
    yield _line(HEADER)
    offset = 0
    while True:
        stored = await stored_findings(run, offset=offset, limit=EXPORT_PAGE)
        for row in stored:
            yield _line(finding_row(row.finding, row.evidence, row.review))
        if len(stored) < EXPORT_PAGE:
            return
        offset += len(stored)
