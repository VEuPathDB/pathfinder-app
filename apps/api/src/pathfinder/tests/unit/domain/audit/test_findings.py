"""What a checked candidate names: the error type and certainty a library answer carries."""

from __future__ import annotations

import re
from itertools import product
from typing import get_args
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError
from veupathdb_mcp.audit import (
    GeneLengthAudit,
    LengthClass,
    LengthVerdict,
    PseudogeneVerdict,
    SecVerdict,
    SelenoproteinEndAudit,
)

from pathfinder.domain.audit.confirmations import (
    LengthConfirmation,
    PseudogeneConfirmation,
    SelenoproteinConfirmation,
)
from pathfinder.domain.audit.findings import (
    NO_ERROR,
    AuditOutcome,
    Classification,
    ConfirmationEvidence,
    EvidencePayload,
    FindingCounts,
    FindingTally,
    GeneEvidencePayload,
    RelativesEvidence,
    classify_confirmation,
)
from pathfinder.tests._support.audit import (
    PIGA_INTACT,
    SELK_STOPS,
    not_checked_audit,
    short_audit,
    split_audit,
)
from pathfinder.tests._support.audit_evidence import K13, K13_EVIDENCE

_PAYLOAD: TypeAdapter[EvidencePayload] = TypeAdapter(EvidencePayload)
_TRUNCATED = Classification(error_type="truncated_model", certainty="high")
_SPLIT = Classification(error_type="split_model", certainty="medium")
_SEC_STOP = Classification(error_type="sec_read_as_stop", certainty="high")
_PSEUDOGENE_ANSWERS = {
    "INTACT": Classification(
        error_type="intact_gene_called_pseudogene", certainty="high"
    ),
    "FRAMESHIFT": NO_ERROR,
    "PREMATURE_STOP": NO_ERROR,
    "START_OR_STOP_LOST": NO_ERROR,
    "NOT_ALIGNED": NO_ERROR,
}
_SELENOPROTEIN_ANSWERS = {
    "CONTAINS_SEC": NO_ERROR,
    "STOPS_AT_SEC": _SEC_STOP,
    "NOT_AT_SEC": NO_ERROR,
    "MODEL_NOT_FOUND": NO_ERROR,
}
_SEC_FACTS: dict[str, dict[str, object]] = {
    "CONTAINS_SEC": {"tail_identity": None, "sec_aligned": None},
    "STOPS_AT_SEC": {},
    "NOT_AT_SEC": {"tail_identity": 0.5, "sec_aligned": True},
    "MODEL_NOT_FOUND": {"tail_identity": None, "sec_aligned": False},
}
_LENGTH_ERRORS = {
    ("SHORT", "GENOME_ENCODES"): _TRUNCATED,
    ("SPLIT", "SPLIT_CONFIRMED"): _SPLIT,
}
_GAPPED_SPLIT = GeneLengthAudit.model_validate(
    {
        **split_audit("G1", "G2", reference_gene="R1").model_dump(),
        "counts": {"part1": 9, "absent": 1, "part2": 9},
        "track": "1" * 9 + "." + "2" * 9,
        "ns_in_window": 40,
    }
)
_LENGTH_CLASSES = get_args(LengthClass.__value__)
_LENGTH_VERDICTS = get_args(LengthVerdict.__value__)


def _length_answer(length_class: str, verdict: str) -> GeneLengthAudit:
    if verdict == "NOT_CHECKED":
        base = not_checked_audit(["G1"], "TYPICAL", reference_gene="R1")
    elif verdict.startswith("SPLIT_"):
        base = split_audit("G1", "G2", reference_gene="R1", verdict=verdict)
    else:
        base = short_audit("G1", reference_gene="R1", verdict=verdict)
    return GeneLengthAudit.model_validate(
        {**base.model_dump(), "length_class": length_class}
    )


def test_every_library_verdict_has_a_named_answer() -> None:
    assert set(_PSEUDOGENE_ANSWERS) == set(get_args(PseudogeneVerdict.__value__))
    assert set(_SELENOPROTEIN_ANSWERS) == set(get_args(SecVerdict.__value__))
    assert set(_LENGTH_CLASSES) == {"SHORT", "LONG", "TYPICAL", "SPLIT", "UNQUALIFIED"}
    assert set(_LENGTH_VERDICTS) == {
        "GENOME_ENCODES",
        "ASSEMBLY",
        "ABSENT",
        "NOT_SHORT",
        "SPLIT_CONFIRMED",
        "SPLIT_UNCLEAR",
        "NOT_CHECKED",
    }


def test_intact_names_a_called_pseudogene_because_the_library_refuses_unflagged_strains() -> (
    None
):
    named = classify_confirmation(PseudogeneConfirmation(result=PIGA_INTACT))
    assert named == Classification(
        error_type="intact_gene_called_pseudogene", certainty="high"
    ), (
        "an INTACT answer exists only for a strain gene its site flags as a "
        "pseudogene: the library refuses a pseudogene-call check on any other gene"
    )


@pytest.mark.parametrize(("verdict", "expected"), _PSEUDOGENE_ANSWERS.items())
def test_each_pseudogene_verdict_names_its_answer(
    verdict: str, expected: Classification
) -> None:
    answer = PIGA_INTACT.model_copy(update={"verdict": verdict})
    assert classify_confirmation(PseudogeneConfirmation(result=answer)) == expected


def test_a_model_that_stops_at_its_sec_codon_is_an_error() -> None:
    named = classify_confirmation(SelenoproteinConfirmation(result=SELK_STOPS))
    assert named == _SEC_STOP


@pytest.mark.parametrize("tail", ["UG", "UGKLMN"])
def test_a_sec_stop_is_high_whatever_the_length_of_its_tail(tail: str) -> None:
    answer = SelenoproteinEndAudit.model_validate(
        {**SELK_STOPS.model_dump(), "reference_tail": tail}
    )
    named = classify_confirmation(SelenoproteinConfirmation(result=answer))
    assert named == _SEC_STOP


@pytest.mark.parametrize(("aligned", "identity"), [(False, 1.0), (True, 0.5)])
def test_the_library_answers_a_sec_stop_only_aligned_and_matched(
    aligned: bool, identity: float
) -> None:
    with pytest.raises(
        ValidationError,
        match=re.escape(
            "a model stops at Sec only when its end aligns before the reference "
            "Sec and the tail is at least 0.8 identical"
        ),
    ):
        SelenoproteinEndAudit.model_validate(
            {
                **SELK_STOPS.model_dump(),
                "sec_aligned": aligned,
                "tail_identity": identity,
            }
        )


@pytest.mark.parametrize(("verdict", "expected"), _SELENOPROTEIN_ANSWERS.items())
def test_each_selenoprotein_verdict_names_its_answer(
    verdict: str, expected: Classification
) -> None:
    answer = SelenoproteinEndAudit.model_validate(
        {**SELK_STOPS.model_dump(), **_SEC_FACTS[verdict], "verdict": verdict}
    )
    assert classify_confirmation(SelenoproteinConfirmation(result=answer)) == expected


@pytest.mark.parametrize(
    ("confirmation", "expected"),
    [
        (
            LengthConfirmation(
                check="gene_length", result=short_audit("G1", reference_gene="R1")
            ),
            _TRUNCATED,
        ),
        (
            LengthConfirmation(
                check="gene_length",
                result=short_audit(
                    "G1", reference_gene="R1", verdict="ASSEMBLY", at_contig_edge=True
                ),
            ),
            NO_ERROR,
        ),
        (
            LengthConfirmation(
                check="gene_length",
                result=short_audit("G1", reference_gene="R1", verdict="ABSENT"),
            ),
            NO_ERROR,
        ),
        (
            LengthConfirmation(
                check="gene_length",
                result=short_audit("G1", reference_gene="R1", verdict="NOT_SHORT"),
            ),
            NO_ERROR,
        ),
        (
            LengthConfirmation(
                check="gene_split",
                result=split_audit("G1", "G2", reference_gene="R1"),
            ),
            _SPLIT,
        ),
        (
            LengthConfirmation(check="gene_split", result=_GAPPED_SPLIT),
            _SPLIT,
        ),
        (
            LengthConfirmation(
                check="gene_split",
                result=split_audit(
                    "G1", "G2", reference_gene="R1", verdict="SPLIT_UNCLEAR"
                ),
            ),
            NO_ERROR,
        ),
        (
            LengthConfirmation(
                check="gene_length",
                result=not_checked_audit(["G1"], "LONG", reference_gene="R1"),
            ),
            NO_ERROR,
        ),
        (
            LengthConfirmation(
                check="gene_length",
                result=not_checked_audit(["G1"], "TYPICAL", reference_gene="R1"),
            ),
            NO_ERROR,
        ),
        (
            LengthConfirmation(
                check="gene_length",
                result=not_checked_audit(["G1"], "UNQUALIFIED", reference_gene="R1"),
            ),
            NO_ERROR,
        ),
        (
            LengthConfirmation(
                check="gene_split",
                result=not_checked_audit(
                    ["G1", "G2"], "UNQUALIFIED", reference_gene="R1"
                ),
            ),
            NO_ERROR,
        ),
    ],
)
def test_a_length_answer_names_its_error(
    confirmation: LengthConfirmation, expected: Classification
) -> None:
    assert classify_confirmation(confirmation) == expected


@pytest.mark.parametrize(
    ("length_class", "verdict"), list(product(_LENGTH_CLASSES, _LENGTH_VERDICTS))
)
def test_only_two_length_answers_name_an_error(length_class: str, verdict: str) -> None:
    answer = _length_answer(length_class, verdict)
    check = "gene_split" if len(answer.genes) == 2 else "gene_length"
    named = classify_confirmation(LengthConfirmation(check=check, result=answer))
    assert named == _LENGTH_ERRORS.get((length_class, verdict), NO_ERROR)


def test_an_error_type_is_never_stored_without_its_certainty() -> None:
    with pytest.raises(ValidationError, match="named together"):
        Classification(error_type="split_model")
    with pytest.raises(ValidationError, match="named together"):
        Classification(certainty="high")


def test_relative_lengths_and_their_tier_are_stored_together() -> None:
    with pytest.raises(
        ValidationError, match="relatives' tier is stored with their lengths"
    ):
        RelativesEvidence(
            reference_gene="R1",
            reference_length=400,
            model_length=200,
            relatives_median=400.0,
            relative_lengths={"P. vivax": 401, "P. knowlesi": 399},
        )
    with pytest.raises(
        ValidationError, match="relatives' tier is stored with their lengths"
    ):
        RelativesEvidence(
            reference_gene="R1",
            reference_length=400,
            model_length=200,
            relatives_median=None,
            relatives_tier="OTHER_GENERA",
        )


def test_evidence_reads_back_by_its_kind() -> None:
    confirmation = ConfirmationEvidence(
        confirmation=PseudogeneConfirmation(result=PIGA_INTACT)
    )
    split = ConfirmationEvidence(
        confirmation=LengthConfirmation(
            check="gene_split", result=split_audit("G1", "G2", reference_gene="R1")
        )
    )
    relatives = RelativesEvidence(
        reference_gene="R1",
        reference_length=400,
        model_length=200,
        relatives_median=400.0,
        relative_lengths={"P. vivax": 401, "P. knowlesi": 399},
        relatives_tier="SAME_GENUS",
        side="STRAIN_SHORT",
    )
    evidence = GeneEvidencePayload(genes=(K13,), evidence=(K13_EVIDENCE,))
    for payload in (confirmation, split, relatives, evidence):
        dumped = _PAYLOAD.dump_python(payload, by_alias=True, mode="json")
        assert _PAYLOAD.validate_python(dumped) == payload
    dumped = _PAYLOAD.dump_python(confirmation, by_alias=True, mode="json")
    assert dumped["confirmation"]["result"]["strainCdsLength"] == 1386
    assert _PAYLOAD.dump_python(relatives, by_alias=True, mode="json") == {
        "kind": "relatives",
        "referenceGene": "R1",
        "referenceLength": 400,
        "modelLength": 200,
        "relativesMedian": 400.0,
        "relativeLengths": {"P. vivax": 401, "P. knowlesi": 399},
        "relativesTier": "SAME_GENUS",
        "side": "STRAIN_SHORT",
        "referenceOrganism": None,
    }
    stored_before_sides = {
        "kind": "relatives",
        "referenceGene": "R1",
        "referenceLength": 400,
        "modelLength": 200,
        "relativesMedian": 400.0,
    }
    assert _PAYLOAD.validate_python(stored_before_sides) == relatives.model_copy(
        update={"side": None, "relative_lengths": {}, "relatives_tier": None}
    )
    (read,) = _PAYLOAD.dump_python(evidence, by_alias=True, mode="json")["evidence"]
    assert (read["gene"], read["pubmed"], read["comments"]) == (K13, 44, 9)


def test_an_error_type_is_counted_only_on_a_confirmed_finding() -> None:
    with pytest.raises(ValidationError, match="only a confirmed finding"):
        FindingTally(
            genome="G",
            check="gene_length",
            status="failed",
            error_type="truncated_model",
            count=3,
            judged=True,
            model_genome="G",
        )


@pytest.mark.parametrize(
    ("check", "result"),
    [
        ("gene_length", split_audit("G1", "G2", reference_gene="R1")),
        ("gene_split", short_audit("G1", reference_gene="R1")),
    ],
)
def test_a_length_confirmation_holds_the_genes_its_check_reads(
    check: str, result: GeneLengthAudit
) -> None:
    with pytest.raises(ValidationError, match="reads"):
        LengthConfirmation.model_validate({"check": check, "result": result})


_RUN = UUID("00000000-0000-0000-0000-000000000007")
_OUTCOME = {
    "run_id": _RUN,
    "status": "finished",
    "requests": 12,
    "unfinished": (),
    "counts": FindingCounts(),
    "failed_genomes": (),
    "unreached_genomes": (),
    "unread_genomes": (),
}


def test_an_outcome_names_the_release_even_when_it_is_unknown() -> None:
    with pytest.raises(ValidationError, match="release"):
        AuditOutcome.model_validate(_OUTCOME)
    unknown = AuditOutcome.model_validate({**_OUTCOME, "release": None})
    known = AuditOutcome.model_validate({**_OUTCOME, "release": "71"})
    assert unknown.model_dump(by_alias=True, mode="json")["release"] is None
    assert known.model_dump(by_alias=True, mode="json")["release"] == "71"
