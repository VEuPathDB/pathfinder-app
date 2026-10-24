from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from pathfinder.domain.audit.findings import Certainty, ErrorType
from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.domain.audit.verdicts import (
    ErrorTypeSection,
    FindingReview,
    GeneModelVerdict,
    LiteratureStatus,
    ReviewAgreement,
    ReviewProgress,
    ReviewStatus,
    Synthesis,
    VerdictKind,
    finding_cite,
)
from pathfinder.persistence.models import AuditFindingRecord
from pathfinder.services.audit.review_views import (
    AgreementView,
    ErrorTypeView,
    FindingLine,
    ReviewLine,
    ReviewState,
    ReviewText,
    agreement_view,
    error_type_views,
    finding_line,
    review_line,
    review_state,
    review_text,
)

_GENOME = "Examplea alpha A"
_OTHER = "Examplea beta B"


def _record(
    finding_id: int,
    error_type: ErrorType | None,
    certainty: Certainty | None,
    impact: float | None,
) -> AuditFindingRecord:
    return AuditFindingRecord(
        id=finding_id,
        run_id=uuid4(),
        genome=_GENOME,
        screened_genome=_OTHER,
        paired_genome=None,
        target=SingleGeneTarget(check="gene_length", genes=(f"EXA_{finding_id:04d}",)),
        sampled=True,
        status="confirmed",
        error_type=error_type,
        certainty=certainty,
        judged=True,
        impact=impact,
        weighing=None,
        requests=1,
        attempts=1,
        stopped=0,
        message=None,
    )


def _review(verdict: VerdictKind = "error", **changed: Any) -> FindingReview:
    named = verdict == "error"
    return FindingReview(
        verdict=GeneModelVerdict(
            genes=("EXA_0001",),
            model_genome=_GENOME,
            verdict=verdict,
            error_type="truncated_model" if named else None,
            certainty="high" if named else None,
            cause="The relatives are longer.",
            cites=(finding_cite(1),),
        ),
        already_known=changed.pop("already_known", "not_searched"),
        card_text="Extend the model to the relatives' stop.",
        **changed,
    )


@pytest.mark.parametrize(
    ("verdict", "text"),
    [
        ("error", "The review keeps the error"),
        ("no_error", "The review finds no error"),
        ("undecided", "The review could not decide"),
    ],
)
def test_a_review_line_states_its_verdict(verdict: VerdictKind, text: str) -> None:
    line = review_line(_review(verdict, second_verdict="no_error"))

    assert line == ReviewLine(
        verdict=verdict,
        verdict_text=text,
        second_verdict="no_error",
        impact=None,
        impact_reason=None,
        literature="not_searched",
        literature_text="The literature was not searched",
    )


@pytest.mark.parametrize(
    ("status", "sources", "text"),
    [
        ("known", ("10.1000/x",), "Already reported"),
        ("not_found", (), "No report of it was found"),
        ("not_searched", (), "The literature was not searched"),
    ],
)
def test_a_review_line_states_its_literature(
    status: LiteratureStatus, sources: tuple[str, ...], text: str
) -> None:
    line = review_line(_review(already_known=status, known_from=sources))

    assert (line.literature, line.literature_text) == (status, text)


def test_a_review_line_carries_the_changed_impact_and_its_reason() -> None:
    line = review_line(_review(impact=0.8, impact_reason="A paper uses the gene."))

    assert (line.impact, line.impact_reason) == (0.8, "A paper uses the gene.")


@pytest.mark.parametrize(
    ("depends", "text"),
    [
        (True, "A published study depends on this gene's model"),
        (False, "No published study was found that depends on this gene's model"),
        (None, "Not checked whether a published study depends on this gene's model"),
    ],
)
def test_a_review_text_states_whether_a_paper_depends_on_it(
    *, depends: bool | None, text: str
) -> None:
    found = review_text(_review("no_error", paper_depends=depends))

    assert found == ReviewText(
        verdict_text="The review finds no error",
        literature_text="The literature was not searched",
        paper_text=text,
        second_text=None,
    )


@pytest.mark.parametrize(
    ("second", "text"),
    [
        ("error", "A second, independent review: The review keeps the error"),
        ("no_error", "A second, independent review: The review finds no error"),
        ("undecided", "A second, independent review: The review could not decide"),
    ],
)
def test_a_review_text_states_the_second_review(second: VerdictKind, text: str) -> None:
    assert review_text(_review(second_verdict=second)).second_text == text


def test_an_agreement_view_states_the_agreement() -> None:
    assert agreement_view(ReviewAgreement(sampled=3, agreed=2)) == AgreementView(
        sampled=3,
        agreed=2,
        share=0.667,
        text="Two independent reviews agreed on 2 of 3 sampled findings (67%)",
    )


def test_an_agreement_of_no_pair_has_no_share() -> None:
    assert agreement_view(ReviewAgreement(sampled=0, agreed=0)) == AgreementView(
        sampled=0,
        agreed=0,
        share=None,
        text="No finding was reviewed twice, so the reviews' agreement is not measured",
    )


@pytest.mark.parametrize(
    ("status", "text"),
    [
        ("waiting", "Reviews are queued"),
        ("reviewing", "Reviewing findings"),
        ("synthesized", "Reviewed and summarized"),
        ("stopped", "Reviews stopped"),
    ],
)
def test_a_review_state_states_its_status(status: ReviewStatus, text: str) -> None:
    progress = ReviewProgress(status=status, done=1, total=3, message="a reason")

    assert review_state(progress) == ReviewState(
        status=status, text=text, done=1, total=3, message="a reason"
    )


def test_a_finding_line_keeps_the_stored_impact_beside_the_reviewed_one() -> None:
    line = finding_line(
        _record(7, "sec_read_as_stop", "medium", 0.4),
        _review(impact=0.9, impact_reason="A paper uses the gene."),
    )

    assert line == FindingLine(
        id=7,
        genes=["EXA_0007"],
        genome=_GENOME,
        error_type="sec_read_as_stop",
        error_title="Selenocysteine codon read as a stop",
        certainty="medium",
        impact=0.4,
        reviewed_impact=0.9,
    )


def test_a_finding_line_with_no_review_or_error_type() -> None:
    line = finding_line(_record(8, None, None, None), None)

    assert (line.error_title, line.reviewed_impact) == (None, None)


def _line(finding_id: int, error_type: ErrorType = "truncated_model") -> FindingLine:
    return finding_line(_record(finding_id, error_type, "high", 0.5), None)


_TALLY: list[tuple[ErrorType, str, Certainty, int]] = [
    ("truncated_model", _GENOME, "low", 2),
    ("truncated_model", _OTHER, "medium", 1),
    ("intact_gene_called_pseudogene", _GENOME, "medium", 1),
    ("missing_exon", _OTHER, "low", 3),
    ("missing_exon", _OTHER, "high", 1),
]


def test_error_types_follow_the_title_order_with_their_tallies() -> None:
    found = error_type_views(_TALLY, None, {})

    assert found == [
        ErrorTypeView(
            error_type="intact_gene_called_pseudogene",
            title="Intact gene called a pseudogene",
            description=(
                "The site calls the gene a pseudogene, but the genome's DNA encodes "
                "the whole protein its reference encodes."
            ),
            count=1,
            genomes=[_GENOME],
            certainty="medium",
            cause=None,
            confirmed_by=None,
            reviewed=[],
        ),
        ErrorTypeView(
            error_type="truncated_model",
            title="Model too short",
            description=(
                "The model's protein is shorter than its orthologs', and the "
                "genome's DNA encodes the part it lacks."
            ),
            count=3,
            genomes=[_GENOME, _OTHER],
            certainty="medium",
            cause=None,
            confirmed_by=None,
            reviewed=[],
        ),
        ErrorTypeView(
            error_type="missing_exon",
            title="Exon missing from the model",
            description="RNA-seq reads join an exon the model does not have.",
            count=4,
            genomes=[_OTHER],
            certainty="high",
            cause=None,
            confirmed_by=None,
            reviewed=[],
        ),
    ]


@pytest.mark.parametrize(
    ("certainties", "highest"),
    [
        (("low", "medium"), "medium"),
        (("medium", "low"), "medium"),
        (("low", "high"), "high"),
        (("high", "medium"), "high"),
        (("low", "low"), "low"),
    ],
)
def test_an_error_type_holds_its_highest_certainty(
    certainties: tuple[Certainty, Certainty], highest: Certainty
) -> None:
    tally: list[tuple[ErrorType, str, Certainty, int]] = [
        ("truncated_model", _GENOME, certainty, 1) for certainty in certainties
    ]

    (view,) = error_type_views(tally, None, {})

    assert view.certainty == highest


def test_an_error_type_reads_its_synthesis_section_in_order() -> None:
    synthesis = Synthesis(
        sections=(
            ErrorTypeSection(
                error_type="truncated_model",
                cause="The models stop early.",
                confirmed_by="The relatives' lengths confirm it.",
                finding_ids=(5, 3),
            ),
        ),
        headline=(3,),
        summary="Two kept.",
        agreement=ReviewAgreement(sampled=0, agreed=0),
    )
    lines = {3: _line(3), 5: _line(5), 9: _line(9, "missing_exon")}

    found = {v.error_type: v for v in error_type_views(_TALLY, synthesis, lines)}

    truncated = found["truncated_model"]
    assert (truncated.cause, truncated.confirmed_by, truncated.reviewed) == (
        "The models stop early.",
        "The relatives' lengths confirm it.",
        [lines[5], lines[3]],
    )
    exon = found["missing_exon"]
    assert (exon.cause, exon.confirmed_by, exon.reviewed) == (None, None, [])
