from __future__ import annotations

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
from pathfinder.services.audit.export import HEADER, finding_row, safe_cell
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


def test_a_cell_a_spreadsheet_would_read_as_a_formula_is_quoted() -> None:
    cells = ["=HYPERLINK(1)", "-3", "+1", "@A1", "\tA1", "\r=A1", PIGA]
    assert [safe_cell(cell) for cell in cells] == [
        "'=HYPERLINK(1)",
        "'-3",
        "'+1",
        "'@A1",
        "'\tA1",
        "'\r=A1",
        PIGA,
    ]


def test_every_cell_of_a_row_is_quoted() -> None:
    hostile = _view(None).model_copy(update={"genome": "=cmd()"})
    assert finding_row(hostile, [], None)[0] == "'=cmd()"
