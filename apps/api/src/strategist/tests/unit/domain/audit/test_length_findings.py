from __future__ import annotations

from itertools import product
from typing import get_args

import pytest
from veupathdb_mcp.audit import (
    FrameChange,
    GeneLengthAudit,
    LengthClass,
    LengthVerdict,
    SplicePair,
)

from strategist.domain.audit.confirmations import LengthConfirmation
from strategist.domain.audit.findings import (
    NO_ERROR,
    Classification,
    ErrorType,
    classify_confirmation,
)
from strategist.tests._support.audit import (
    FRAMESHIFT,
    not_checked_audit,
    revised,
    short_audit,
    split_audit,
)

_TRUNCATED = Classification(error_type="truncated_model", certainty="high")
_SPLIT = Classification(error_type="split_model", certainty="medium")
_FRAMESHIFT = Classification(error_type="sequence_frameshift", certainty="medium")
_OTHER_FRAME = Classification(error_type="part_in_other_frame", certainty="medium")
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
    ("SHORT", "FRAMESHIFT"): _FRAMESHIFT,
    ("SHORT", "OTHER_FRAME"): _OTHER_FRAME,
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


_PAIRED = FRAMESHIFT.model_copy(
    update={"splice_pair": SplicePair(motif="GT..AG", donor=10, acceptor=40)}
)


def _with_changes(verdict: str, changes: list[FrameChange]) -> LengthConfirmation:
    answer = short_audit("G1", reference_gene="R1", verdict=verdict)
    return LengthConfirmation(
        check="gene_length", result=revised(answer, frame_changes=changes)
    )


_KEPT = FRAMESHIFT.model_copy(update={"shift": 3})
_KEPT_AT_A_PAIR = _PAIRED.model_copy(update={"shift": 108})


def _with_unlisted(
    verdict: str, changes: list[FrameChange], unlisted: list[FrameChange]
) -> LengthConfirmation:
    answer = short_audit("G1", reference_gene="R1", verdict=verdict)
    return LengthConfirmation(
        check="gene_length",
        result=revised(answer, frame_changes=changes, unlisted_changes=unlisted),
    )


def test_a_jump_that_keeps_the_frame_with_no_pair_leaves_a_truncation_high() -> None:
    assert classify_confirmation(_with_changes("GENOME_ENCODES", [_KEPT])) == _TRUNCATED


def test_a_jump_that_keeps_the_frame_at_a_pair_lowers_a_truncation() -> None:
    assert classify_confirmation(
        _with_changes("GENOME_ENCODES", [_KEPT_AT_A_PAIR])
    ) == Classification(error_type="truncated_model", certainty="medium")


def test_a_pair_past_the_cap_lowers_a_truncation() -> None:
    assert classify_confirmation(
        _with_unlisted("GENOME_ENCODES", [_KEPT], [_KEPT_AT_A_PAIR])
    ) == Classification(error_type="truncated_model", certainty="medium")


def test_a_jump_with_no_pair_past_the_cap_rules_out_a_missed_exon() -> None:
    assert classify_confirmation(
        _with_unlisted("OTHER_FRAME", [_PAIRED], [FRAMESHIFT])
    ) == Classification(error_type="part_in_other_frame", certainty="medium")


def test_a_part_with_a_stop_in_it_lowers_a_truncation() -> None:
    answer = short_audit("G1", reference_gene="R1", verdict="GENOME_ENCODES")
    assert classify_confirmation(
        LengthConfirmation(
            check="gene_length", result=revised(answer, part_open=False, part_stop=900)
        )
    ) == Classification(error_type="truncated_model", certainty="medium")


def test_a_truncation_with_a_change_further_out_is_medium() -> None:
    assert classify_confirmation(
        _with_changes("GENOME_ENCODES", [FRAMESHIFT])
    ) == Classification(error_type="truncated_model", certainty="medium")


def test_a_truncation_with_no_change_is_high() -> None:
    assert classify_confirmation(_with_changes("GENOME_ENCODES", [])) == _TRUNCATED


@pytest.mark.parametrize(
    ("changes", "error_type"),
    [
        ([_PAIRED], "possible_missed_exon"),
        ([_PAIRED, _PAIRED], "possible_missed_exon"),
        ([_PAIRED, FRAMESHIFT], "part_in_other_frame"),
        ([_KEPT, _PAIRED, _PAIRED], "part_in_other_frame"),
        ([_KEPT_AT_A_PAIR, _PAIRED], "possible_missed_exon"),
        ([FRAMESHIFT], "part_in_other_frame"),
        ([], "part_in_other_frame"),
    ],
)
def test_a_part_in_another_frame_names_a_missed_exon_only_with_a_pair_at_each_change(
    changes: list[FrameChange], error_type: ErrorType
) -> None:
    assert classify_confirmation(
        _with_changes("OTHER_FRAME", changes)
    ) == Classification(error_type=error_type, certainty="medium")


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
                result=short_audit("G1", reference_gene="R1", verdict="FRAMESHIFT"),
            ),
            _FRAMESHIFT,
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
def test_only_four_length_answers_name_an_error(
    length_class: str, verdict: str
) -> None:
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
