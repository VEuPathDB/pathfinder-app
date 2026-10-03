"""A request for genes is met by a strategy on the transcript class: the site
counts a transcript answer in genes. The code judges each record-type row from
the strategy's record class, whatever the checker wrote."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS
from pathfinder.ai.lead.verify_review import ReviewRecord, review_held_to_the_turn
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import requirement

_ASKED = "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3."
_SIGNAL = (
    "Find Toxoplasma gondii ME49 genes whose proteins have a predicted signal peptide."
)


def _spec(record_type: str) -> OperationalSpec:
    return OperationalSpec(
        goal="odorant-binding proteins on chromosome 3",
        record_type=record_type,
        criteria=[
            Criterion(
                id="c_obp",
                text="odorant-binding protein",
                search_name="GenesByInterproDomain",
            ),
            Criterion(id="c_chr3", text="chromosome 3", search_name="GenesByLocation"),
        ],
    )


def _record(
    spec: OperationalSpec,
    requirements: Sequence[Constraint] = (
        requirement(ConstraintKind.RECORD_TYPE, "record type", "genes"),
    ),
    asked: str = _ASKED,
) -> ReviewRecord:
    return ReviewRecord(
        messages=(asked,),
        requirements=requirements,
        spec=spec,
        read_as=lambda reference: None,
        record_url=lambda gene_id: gene_id,
    )


_GENES_ROW = RequirementCheck(
    text="genes",
    turn=1,
    how="parameter",
    status="unmet",
    note="The built strategy's record type is transcript, not genes.",
)


def _held(row: RequirementCheck, record: ReviewRecord) -> RequirementCheck:
    return review_held_to_the_turn(
        VerificationReview(requirements=[row]), record
    ).requirements[0]


def test_genes_is_met_by_the_transcript_class() -> None:
    row = _held(_GENES_ROW, _record(_spec("transcript")))

    assert (row.status, row.answered_by, row.note) == (
        "met",
        ["c_obp", "c_chr3"],
        "the strategy returns genes",
    )


def test_a_class_counted_in_another_noun_fails_the_stated_genes() -> None:
    row = _held(_GENES_ROW, _record(_spec("snp")))

    assert (row.status, row.answered_by, row.note) == (
        "unmet",
        [],
        "the strategy returns snps",
    )


@pytest.mark.parametrize("text", ["genes", "gene records", "Gene-level data type"])
def test_a_genes_row_with_no_stated_record_type_is_met_by_the_transcript_class(
    text: str,
) -> None:
    """The classifier recorded the organism and the signal peptide only."""
    stated = (
        requirement(ConstraintKind.ORGANISM, "organism", "Toxoplasma gondii ME49"),
        requirement(
            ConstraintKind.OTHER,
            "predicted signal peptide",
            "proteins have a predicted signal peptide",
        ),
    )
    checked = RequirementCheck(
        text=text,
        turn=1,
        how="parameter",
        status="unmet",
        note="The strategy record type is `transcript`, not `gene`.",
    )

    row = _held(checked, _record(_spec("transcript"), stated, _SIGNAL))

    assert (row.status, row.note) == ("met", "the strategy returns genes")


def test_a_stated_pathways_on_a_gene_strategy_is_unmet_whatever_the_checker_wrote() -> (
    None
):
    checked = RequirementCheck(
        text="pathways",
        turn=1,
        answered_by=["c_obp"],
        how="parameter",
        status="met",
        note="the strategy returns pathways",
    )
    stated = (requirement(ConstraintKind.RECORD_TYPE, "record type", "pathways"),)

    row = _held(checked, _record(_spec("transcript"), stated))

    assert (row.status, row.answered_by, row.note) == (
        "unmet",
        [],
        "the strategy returns genes",
    )


def test_a_pathways_row_with_no_stated_record_type_stays_unmet() -> None:
    checked = RequirementCheck(
        text="pathways", turn=1, how="parameter", status="unmet", note="no pathways"
    )

    assert _held(checked, _record(_spec("transcript"), ())) == checked


def test_the_check_leaves_the_record_type_to_the_runtime() -> None:
    text = " ".join(_VERIFICATION_INSTRUCTIONS.split())

    assert (
        "The record type is the runtime's to judge: it marks each record-type row "
        "from the strategy's record class."
    ) in text
    assert "a request for genes on the transcript class is met" in text


def _gene_type_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="protein-coding genes in 3D7",
        record_type="transcript",
        criteria=[
            Criterion(
                id="step_75b174d6",
                text="protein coding genes",
                search_name="GenesByGeneType",
            )
        ],
    )


def test_a_stated_value_of_a_record_noun_is_a_value_row() -> None:
    """A record noun with other words names a value of the record, not a class."""
    checked = RequirementCheck(
        text="protein-coding genes",
        turn=1,
        answered_by=["step_75b174d6"],
        how="parameter",
        status="met",
    )
    stated = (
        requirement(ConstraintKind.RECORD_TYPE, "record type", "protein-coding genes"),
    )
    asked = "How many protein-coding genes does 3D7 have?"

    assert _held(checked, _record(_gene_type_spec(), stated, asked)) == checked


def test_a_record_type_value_that_qualifies_a_record_noun_is_recorded_as_other() -> (
    None
):
    stated = requirement(
        ConstraintKind.RECORD_TYPE, "record type", "protein-coding genes"
    )

    assert stated.kind is ConstraintKind.OTHER


@pytest.mark.parametrize("value", ["genes", "pathways", "Gene-level data type"])
def test_a_record_type_value_that_names_a_record_class_keeps_its_kind(
    value: str,
) -> None:
    stated = requirement(ConstraintKind.RECORD_TYPE, "record type", value)

    assert stated.kind is ConstraintKind.RECORD_TYPE


def test_transcripts_is_met_by_the_transcript_class() -> None:
    checked = _GENES_ROW.model_copy(update={"text": "transcripts"})

    row = _held(checked, _record(_spec("transcript"), ()))

    assert (row.status, row.note) == ("met", "the strategy returns genes")
