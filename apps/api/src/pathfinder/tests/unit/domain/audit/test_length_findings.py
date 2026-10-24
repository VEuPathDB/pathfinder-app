from __future__ import annotations

from itertools import product
from typing import get_args

import pytest
from veupathdb_mcp.audit import GeneLengthAudit, LengthClass, LengthVerdict

from pathfinder.domain.audit.confirmations import LengthConfirmation
from pathfinder.domain.audit.findings import (
    NO_ERROR,
    Classification,
    classify_confirmation,
)
from pathfinder.tests._support.audit import (
    not_checked_audit,
    short_audit,
    split_audit,
)

_TRUNCATED = Classification(error_type="truncated_model", certainty="high")
_SPLIT = Classification(error_type="split_model", certainty="medium")
_LENGTH_UNREAD = Classification(
    message=(
        "NOT_CHECKED: the ortholog group does not class the gene as short, so the "
        "check reads no DNA"
    )
)
_LENGTH_UNCLASSED = Classification(
    message=(
        "NOT_CHECKED: the ortholog group cannot class the gene's length, so the "
        "check reads no DNA"
    )
)
_SPLIT_UNCLASSED = Classification(
    message=(
        "NOT_CHECKED: the ortholog group cannot class the pair's length, so the "
        "check reads no DNA"
    )
)
_SPLIT_UNREAD = Classification(
    message=(
        "NOT_CHECKED: the ortholog group does not call the pair a split, so the "
        "check reads no DNA"
    )
)
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
            _LENGTH_UNREAD,
        ),
        (
            LengthConfirmation(
                check="gene_length",
                result=not_checked_audit(["G1"], "TYPICAL", reference_gene="R1"),
            ),
            _LENGTH_UNREAD,
        ),
        (
            LengthConfirmation(
                check="gene_length",
                result=not_checked_audit(["G1"], "UNQUALIFIED", reference_gene="R1"),
            ),
            _LENGTH_UNCLASSED,
        ),
        (
            LengthConfirmation(
                check="gene_split",
                result=not_checked_audit(
                    ["G1", "G2"], "UNQUALIFIED", reference_gene="R1"
                ),
            ),
            _SPLIT_UNCLASSED,
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
    unread = {
        ("gene_length", False): _LENGTH_UNREAD,
        ("gene_length", True): _LENGTH_UNCLASSED,
        ("gene_split", False): _SPLIT_UNREAD,
        ("gene_split", True): _SPLIT_UNCLASSED,
    }[check, length_class == "UNQUALIFIED"]
    expected = unread if verdict == "NOT_CHECKED" else NO_ERROR
    assert named == _LENGTH_ERRORS.get((length_class, verdict), expected)
    assert named.judged is (verdict != "NOT_CHECKED")
