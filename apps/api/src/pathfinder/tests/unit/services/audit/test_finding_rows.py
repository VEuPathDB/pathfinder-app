from __future__ import annotations

import csv
import io
import unicodedata

import pytest

from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    EvidenceKind,
    EvidencePayload,
    EvidenceStatus,
    GeneEvidencePayload,
)
from pathfinder.domain.audit.scope import GenePairTarget
from pathfinder.domain.audit.verdicts import FindingReview, GeneModelVerdict
from pathfinder.persistence.models import AuditEvidenceRecord
from pathfinder.services.audit.export import (
    HEADER,
    csv_line,
    finding_row,
    safe_cell,
)
from pathfinder.services.audit.finding_views import FindingView, GeneLink
from pathfinder.services.audit.review_views import review_line
from pathfinder.tests._support.audit import NF54, NF54_PIGA, PIGA, PIGA_INTACT
from pathfinder.tests._support.audit_evidence import PIGA_EVIDENCE

_CAUSE = "The strain's DNA encodes all 1,386 bases with no stop inside."
_FIX = "Annotate the gene as protein coding."
_NF54_PAGE = f"https://qa.plasmodb.org/plasmo.qa/app/record/gene/{NF54_PIGA}"
_PIGA_PAGE = f"https://qa.plasmodb.org/plasmo.qa/app/record/gene/{PIGA}"


def _review() -> FindingReview:
    return FindingReview(
        verdict=GeneModelVerdict(
            genes=(NF54_PIGA, PIGA),
            model_genome=NF54,
            verdict="error",
            error_type="intact_gene_called_pseudogene",
            certainty="high",
            cause=_CAUSE,
            cites=("finding:1",),
        ),
        already_known="known",
        known_from=("PMID:1", "PMID:2"),
        card_text=_FIX,
        impact=0.8,
        impact_reason="The reference gene's record cites two articles.",
        second_verdict="no_error",
    )


def _view(review: FindingReview | None) -> FindingView:
    return FindingView(
        id=1,
        genome=NF54,
        screened_genome=NF54,
        paired_genome=None,
        target=GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA)),
        sampled=True,
        status="confirmed",
        error_type="intact_gene_called_pseudogene",
        certainty="high",
        judged=True,
        impact=0.5,
        weighing=None,
        requests=6,
        attempts=1,
        stopped=0,
        message=None,
        reviewed=review is not None,
        verdict="INTACT",
        from_target=False,
        review_line=None if review is None else review_line(review),
        genes=[
            GeneLink(gene=NF54_PIGA, url=_NF54_PAGE),
            GeneLink(gene=PIGA, url=_PIGA_PAGE),
        ],
    )


def _evidence(
    kind: EvidenceKind, status: EvidenceStatus, payload: EvidencePayload | None
) -> AuditEvidenceRecord:
    return AuditEvidenceRecord(
        finding_id=1,
        kind=kind,
        status=status,
        payload=payload,
        requests=1,
        attempts=1,
        stopped=0,
        message=None,
    )


_CONFIRMATION = _evidence(
    "confirmation",
    "stored",
    ConfirmationEvidence(confirmation=PseudogeneConfirmation(result=PIGA_INTACT)),
)
_RECORDS = _evidence(
    "gene_evidence",
    "stored",
    GeneEvidencePayload(genes=(PIGA,), evidence=(PIGA_EVIDENCE,)),
)


def test_a_row_states_the_finding_as_the_page_does() -> None:
    row = finding_row(_view(_review()), [_RECORDS, _CONFIRMATION], _review())
    assert row[:12] == [
        NF54,
        f"{NF54_PIGA}; {PIGA}",
        "Pseudogene calls on intact genes",
        "Intact gene called a pseudogene",
        "The strain's DNA encodes the whole protein, so the pseudogene call is wrong",
        "0.5",
        "The review keeps the error",
        "The review finds no error",
        _CAUSE,
        "Already reported; PMID:1; PMID:2",
        "0.8",
        _FIX,
    ]
    assert row[12].startswith("Reference coding sequence: 1,386 bases; ")
    assert f"; {PIGA} citations: " in row[12]
    assert row[13] == f"{_NF54_PAGE}; {_PIGA_PAGE}"
    assert len(row) == len(HEADER)


def test_a_finding_with_no_review_reads_not_reviewed() -> None:
    row = finding_row(_view(None), [_CONFIRMATION], None)
    assert row[6:12] == ["Not reviewed", "", "", "", "", ""]


def test_a_finding_no_check_settled_reads_why_in_words() -> None:
    unread = _view(None).model_copy(
        update={"status": "unread", "verdict": None, "error_type": None}
    )
    row = finding_row(
        unread,
        [
            _evidence("confirmation", "unread", None),
            _evidence("gene_evidence", "unreached", None),
            _evidence("relatives", "failed", None),
        ],
        None,
    )
    assert [row[3], row[4]] == ["", "Not checked: not read before the run's deadline"]
    assert row[12] == (
        "What the genome's DNA shows: Not read before the run's deadline; "
        "What the site's gene records hold: The site did not answer; "
        "Lengths in related genomes: Could not be read"
    )


def _parsed(line: str, delimiter: str = ",") -> list[str]:
    (row,) = csv.reader(io.StringIO(line), delimiter=delimiter)
    return row


def _genome_cell(text: str) -> str:
    row = finding_row(_view(None).model_copy(update={"genome": text}), [], None)
    return _parsed(csv_line(row))[0]


def _fields(line: str, delimiter: str) -> list[str]:
    reader = csv.reader(io.StringIO(line, newline=""), delimiter=delimiter)
    return [field for row in reader for field in row]


def _starts_a_formula(field: str) -> bool:
    marks = (
        c
        for c in unicodedata.normalize("NFKC", field)
        if not unicodedata.category(c).startswith(("C", "Z"))
    )
    return next(marks, "") in frozenset("=+-@")


@pytest.mark.parametrize(
    "text",
    ["=A1", "+1", "-3", "@A1", " =A1", "\u200b=A1", "\uff1dA1"],
)
def test_a_cell_a_spreadsheet_would_read_as_a_formula_is_quoted(text: str) -> None:
    assert _genome_cell(text) == f"'{text}"


@pytest.mark.parametrize(
    ("text", "written"),
    [
        ("\n=A1", "'\n'=A1"),
        ("\r=A1", "'\r'=A1"),
        ("\t=A1", "'\t'=A1"),
        ("x;=A1;", "x;'=A1;"),
        ("x\n=A1", "x\n'=A1"),
        ("x\t+A1", "x\t'+A1"),
        ("x\r@A1", "x\r'@A1"),
        ("x; -A1", "x; '-A1"),
        ("x;\u00a0\uff1dA1", "x;\u00a0'\uff1dA1"),
        ("x;\u200b=A1", "x;\u200b'=A1"),
        ('x;"=A1', "x;\"'=A1"),
        ("x;;=A1", "x;;'=A1"),
        ("x; \n=A1", "x; \n'=A1"),
        ("x;=A1;=B2", "x;'=A1;'=B2"),
    ],
)
def test_a_trigger_after_a_separator_is_neutralized_in_place(
    text: str, written: str
) -> None:
    assert safe_cell(text) == written


@pytest.mark.parametrize(
    "text",
    [
        PIGA,
        "Plasmodium falciparum NF54",
        "a=b",
        "x, =A1",
        "x,=A1",
        "a=b; c-d",
        "1-2; 3-4",
        "x;y",
        "PF3D7_1032400; PF3D7_1133400",
        "Already reported; PMID:1; PMID:2",
        "\tA1",
        "x\ny",
        "",
    ],
)
def test_text_with_no_such_pattern_is_byte_identical(text: str) -> None:
    assert safe_cell(text) == text
    assert csv_line([safe_cell(text)]) == f'"{text}"\r\n'


@pytest.mark.parametrize(
    "hostile", ["x;=A1;", "x\n=A1", "x\t+A1", "x; -A1", 'x;"=A1', "\n=A1", ";=A1"]
)
@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_no_parsed_text_field_starts_a_formula(hostile: str, delimiter: str) -> None:
    review = _review()
    review = review.model_copy(
        update={
            "verdict": review.verdict.model_copy(update={"cause": hostile}),
            "card_text": hostile,
        }
    )
    view = _view(review).model_copy(
        update={"genes": [GeneLink(gene=hostile, url=hostile)]}
    )
    line = csv_line(finding_row(view, [], review))
    fields = _fields(line, delimiter)
    assert [field for field in fields if _starts_a_formula(field)] == []


def test_a_comma_parser_reads_each_hostile_cell_whole() -> None:
    view = _view(None).model_copy(update={"genes": [GeneLink(gene="x;=A1;", url="u")]})
    row = _fields(csv_line(finding_row(view, [], None)), ",")
    assert dict(zip(HEADER, row, strict=True))["Gene IDs"] == "x;'=A1;"


def test_every_field_is_quoted() -> None:
    assert csv_line(["x;'=A1;", "plain", ""]) == '"x;\'=A1;","plain",""\r\n'


def test_every_text_column_is_quoted() -> None:
    hostile = "\n=A1"
    review = _review()
    review = review.model_copy(
        update={
            "verdict": review.verdict.model_copy(update={"cause": hostile}),
            "card_text": hostile,
        }
    )
    view = _view(review).model_copy(
        update={"genome": hostile, "genes": [GeneLink(gene=hostile, url=hostile)]}
    )
    row = _parsed(csv_line(finding_row(view, [], review)))
    columns = dict(zip(HEADER, row, strict=True))
    for column in ("Genome", "Gene IDs", "Cause", "Fix", "Gene pages"):
        assert columns[column] == "'\n'=A1"


def test_a_number_the_export_writes_stays_a_number() -> None:
    review = _review().model_copy(update={"impact": -0.25})
    view = _view(review).model_copy(update={"impact": -0.5})
    row = _parsed(csv_line(finding_row(view, [], review)))
    columns = dict(zip(HEADER, row, strict=True))
    assert [columns["Impact"], columns["Impact after review"]] == ["-0.5", "-0.25"]
