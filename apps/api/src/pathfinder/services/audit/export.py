"""One audit run's findings as CSV rows a curator reads in a spreadsheet, in the words of the report page."""

from __future__ import annotations

import csv
import io
import unicodedata
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
_NUMBER_COLUMNS = frozenset({"Impact", "Impact after review"})
_FORMULA = frozenset("=+-@")
_BLANK_CATEGORIES = ("C", "Z")
_SEPARATORS = frozenset(";\t\r\n")
_QUOTE = '"'


def _mark(char: str) -> str:
    return unicodedata.normalize("NFKC", char)[:1]


def _is_blank(char: str) -> bool:
    return unicodedata.category(_mark(char)).startswith(_BLANK_CATEGORIES)


def _neutralized_inside(text: str) -> str:
    written: list[str] = []
    armed = False
    for char in text:
        if armed and char != _QUOTE and not _is_blank(char):
            if _mark(char) in _FORMULA:
                written.append("'")
            armed = False
        armed = armed or char in _SEPARATORS
        written.append(char)
    return "".join(written)


def safe_cell(text: str) -> str:
    inside = _neutralized_inside(text)
    first = next((char for char in text if not _is_blank(char)), "")
    return f"'{inside}" if _mark(first) in _FORMULA else inside


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
    return [
        cell if column in _NUMBER_COLUMNS else safe_cell(cell)
        for column, cell in zip(HEADER, cells, strict=True)
    ]


def csv_line(cells: list[str]) -> str:
    out = io.StringIO()
    csv.writer(out, quoting=csv.QUOTE_ALL).writerow(cells)
    return out.getvalue()


async def finding_lines(run: AuditRunRecord) -> AsyncIterator[str]:
    yield csv_line(HEADER)
    offset = 0
    while True:
        stored = await stored_findings(run, offset=offset, limit=EXPORT_PAGE)
        for row in stored:
            yield csv_line(finding_row(row.finding, row.evidence, row.review))
        if len(stored) < EXPORT_PAGE:
            return
        offset += len(stored)
