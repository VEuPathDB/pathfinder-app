"""What a fusion, strain, missing-gene or organelle answer names, and what it could not judge."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError
from veupathdb_mcp.audit import (
    FusionVerdict,
    MissingVerdict,
    NotRead,
    OrganelleVerdict,
    SideVerdict,
    judged_side,
    missing_verdict,
)

from pathfinder.domain.audit.confirmations import (
    FusionConfirmation,
    MissingGeneConfirmation,
    OrganelleConfirmation,
    StrainConfirmation,
)
from pathfinder.domain.audit.findings import (
    NO_ERROR,
    Classification,
    ConfirmationEvidence,
    EvidencePayload,
    classify_confirmation,
)
from pathfinder.tests._support.audit import gene_row
from pathfinder.tests._support.audit_answers import (
    GT1,
    fusion,
    missing,
    not_long,
    organelle,
    strain,
    unread_strain,
)

_PAYLOAD: TypeAdapter[EvidencePayload] = TypeAdapter(EvidencePayload)
_FUSIONS = {
    "EXTRA_MATCHES_NEIGHBOUR": Classification(
        error_type="fused_model", certainty="high"
    ),
    "EXTRA_UNEXPLAINED": Classification(
        error_type="over_extended_model", certainty="low"
    ),
    "NO_EXTRA": NO_ERROR,
}
_SIDES = {
    "STRAIN_SHORT": Classification(
        error_type="truncated_model", certainty="high", model_role="strain"
    ),
    "REFERENCE_LONG": Classification(
        error_type="over_extended_model", certainty="medium", model_role="reference"
    ),
    "UNCLEAR": NO_ERROR,
    "NO_RELATIVES": Classification(
        message=(
            "NO_RELATIVES: the ortholog group has no independent relatives "
            "(PARALOGS) to judge which side is wrong"
        )
    ),
    "NOT_JUDGED": Classification(
        message=(
            "NOT_JUDGED: the strain's genome answers ABSENT for the run its model "
            "lost, so the check judges no side"
        )
    ),
}
_MISSING = {
    "IN_DNA_UNANNOTATED": Classification(error_type="missing_gene", certainty="high"),
    "IN_DNA_OTHER_MODEL": Classification(error_type="missing_gene", certainty="medium"),
    "PARTIAL": Classification(error_type="missing_gene", certainty="low"),
    "NOT_IN_DNA": NO_ERROR,
    "GAP": Classification(
        message=(
            "GAP: the absent genome has an assembly gap at the locus, so the check "
            "cannot judge whether its DNA holds the gene"
        )
    ),
    "NO_SYNTENY": Classification(
        message=(
            "NO_SYNTENY: no conserved neighbours anchor the locus in the absent "
            "genome, so the check read no DNA"
        )
    ),
    "ANNOTATED_IN_GENOME": Classification(
        message=(
            "ANNOTATED_IN_GENOME: the absent genome annotates members of the "
            "gene's ortholog group, so the gene is not missing"
        )
    ),
}
_ORGANELLES = {
    "SPLIT_AT_JOIN": Classification(
        error_type="organelle_split_at_join", certainty="high"
    ),
    "INTACT_ON_THE_LINE": NO_ERROR,
    "NOT_FOUND": Classification(
        message=(
            "NOT_FOUND: the contig encodes no whole copy of the reference protein, "
            "on the line or across the join, so the check cannot judge a split"
        )
    ),
}


def test_every_library_verdict_has_a_named_answer() -> None:
    assert set(_FUSIONS) == set(get_args(FusionVerdict.__value__))
    assert set(_SIDES) == set(get_args(SideVerdict.__value__))
    assert set(_MISSING) == set(get_args(MissingVerdict.__value__))
    assert set(_ORGANELLES) == set(get_args(OrganelleVerdict.__value__))


@pytest.mark.parametrize(("verdict", "expected"), _FUSIONS.items())
def test_a_fusion_answer_names_its_error(
    verdict: FusionVerdict, expected: Classification
) -> None:
    confirmation = FusionConfirmation(result=fusion(verdict))
    assert classify_confirmation(confirmation) == expected
    assert confirmation.verdict == verdict


_NOT_LONG = "the gene is not LONG, so the fusion check reads no extra residues"


@pytest.mark.parametrize(
    ("length_class", "ratio", "message"),
    [
        ("TYPICAL", 1.0, f"TYPICAL: {_NOT_LONG}"),
        ("SHORT", 0.4, f"SHORT: {_NOT_LONG}"),
        (
            "UNQUALIFIED",
            0.6,
            (
                "UNQUALIFIED: the ortholog group cannot class the gene's length, "
                "so the fusion check reads no extra residues"
            ),
        ),
    ],
)
def test_a_gene_that_is_not_long_is_not_judged_a_fusion(
    length_class: str, ratio: float, message: str
) -> None:
    confirmation = FusionConfirmation(result=not_long(length_class, ratio))
    assert classify_confirmation(confirmation) == Classification(message=message)
    assert confirmation.verdict == length_class


@pytest.mark.parametrize(("side", "expected"), _SIDES.items())
def test_a_strain_answer_names_its_error_by_its_side(
    side: SideVerdict, expected: Classification
) -> None:
    confirmation = StrainConfirmation(result=strain(side))
    assert classify_confirmation(confirmation) == expected
    assert confirmation.verdict == side


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        (
            "NO_LOST_RUN",
            (
                "NOT_JUDGED: the strain protein lacks no run of the reference protein, "
                "so the check reads no genome and judges no side"
            ),
        ),
        (
            "UNQUALIFIED",
            (
                "NOT_JUDGED: the pair's ortholog group is a residual group, not an "
                "orthology group, so the check reads no genome and judges no side"
            ),
        ),
        (
            "PARALOG_IN_WINDOW",
            (
                "NOT_JUDGED: the paralog PcyM_0736800 lies in the window the check "
                "reads, so the check reads no genome and judges no side"
            ),
        ),
    ],
)
def test_a_strain_genome_not_read_says_why(reason: NotRead, message: str) -> None:
    answer = unread_strain(reason)
    assert answer.dna.verdict == "NOT_CHECKED"
    confirmation = StrainConfirmation(result=answer)
    assert classify_confirmation(confirmation) == Classification(message=message)
    assert confirmation.verdict == "NOT_JUDGED"


def test_a_model_role_is_named_only_with_its_error() -> None:
    with pytest.raises(ValidationError, match="model role"):
        Classification(model_role="reference")


@pytest.mark.parametrize("side", list(_SIDES))
def test_each_strain_answer_is_the_side_the_library_judges(side: SideVerdict) -> None:
    answer = strain(side)
    assert (
        judged_side(
            answer.dna.verdict,
            answer.reference_length,
            answer.strain_length,
            answer.relatives.median,
        )
        == side
    )


@pytest.mark.parametrize(("verdict", "expected"), _MISSING.items())
def test_a_missing_gene_answer_names_its_error(
    verdict: MissingVerdict, expected: Classification
) -> None:
    confirmation = MissingGeneConfirmation(result=missing(verdict))
    assert classify_confirmation(confirmation) == expected
    assert confirmation.verdict == verdict


@pytest.mark.parametrize(
    "verdict", ["IN_DNA_UNANNOTATED", "IN_DNA_OTHER_MODEL", "PARTIAL", "GAP"]
)
def test_each_read_missing_answer_is_the_verdict_the_library_calls(
    verdict: MissingVerdict,
) -> None:
    answer = missing(verdict)
    assert answer.located is not None
    overlapping = [
        gene_row(gene.gene, GT1, gene.protein_length)
        for gene in answer.overlapping or []
    ]
    assert missing_verdict(answer.located, overlapping) == verdict


@pytest.mark.parametrize(("verdict", "expected"), _ORGANELLES.items())
def test_an_organelle_answer_names_its_error(
    verdict: OrganelleVerdict, expected: Classification
) -> None:
    confirmation = OrganelleConfirmation(result=organelle(verdict))
    assert classify_confirmation(confirmation) == expected
    assert confirmation.verdict == verdict


def test_a_classification_names_an_error_or_what_was_not_judged_never_both() -> None:
    with pytest.raises(ValidationError, match="not both"):
        Classification(
            error_type="missing_gene", certainty="high", message="GAP: a gap"
        )


@pytest.mark.parametrize(
    "confirmation",
    [
        FusionConfirmation(result=fusion("EXTRA_MATCHES_NEIGHBOUR")),
        FusionConfirmation(result=not_long("TYPICAL", 1.0)),
        StrainConfirmation(result=strain("STRAIN_SHORT")),
        MissingGeneConfirmation(result=missing("IN_DNA_UNANNOTATED")),
        MissingGeneConfirmation(result=missing("ANNOTATED_IN_GENOME")),
        OrganelleConfirmation(result=organelle("SPLIT_AT_JOIN")),
    ],
)
def test_a_stored_answer_reads_back_as_it_was_checked(
    confirmation: FusionConfirmation
    | StrainConfirmation
    | MissingGeneConfirmation
    | OrganelleConfirmation,
) -> None:
    evidence = ConfirmationEvidence(confirmation=confirmation)
    dumped = _PAYLOAD.dump_python(evidence, by_alias=True, mode="json")
    assert _PAYLOAD.validate_python(dumped) == evidence
    assert dumped["confirmation"]["check"] == confirmation.check
