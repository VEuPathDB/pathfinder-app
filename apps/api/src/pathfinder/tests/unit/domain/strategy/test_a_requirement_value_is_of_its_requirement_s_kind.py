from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    DataTypeValue,
    FoldChangeValue,
    PercentileValue,
    RecordTypeValue,
    SignificanceValue,
    UntypedValue,
)


def _constraint(kind: ConstraintKind, value: object) -> Constraint:
    return Constraint.model_validate(
        {"kind": kind, "requestedValue": "top 10%", "label": "x", "value": value}
    )


@pytest.mark.parametrize(
    ("kind", "value", "typed"),
    [
        (
            ConstraintKind.PERCENTILE,
            {"kind": "percentile", "end": "top", "share": 10},
            PercentileValue(end="top", share=10),
        ),
        (
            ConstraintKind.FOLD_CHANGE,
            {"kind": "fold_change", "cut": 1, "scale": "log2", "direction": "up"},
            FoldChangeValue(cut=1, scale="log2", direction="up"),
        ),
        (
            ConstraintKind.STATISTICAL_THRESHOLD,
            {"kind": "statistical_threshold", "statistic": "fdr", "atMost": 0.05},
            SignificanceValue(statistic="fdr", at_most=0.05),
        ),
        (
            ConstraintKind.DATA_TYPE,
            {"kind": "data_type", "data": "rna_seq"},
            DataTypeValue(data="rna_seq"),
        ),
        (
            ConstraintKind.RECORD_TYPE,
            {"kind": "record_type", "recordClass": "group"},
            RecordTypeValue(record_class="group", role="answer"),
        ),
        (
            ConstraintKind.OTHER,
            {"kind": "other", "text": "secreted"},
            UntypedValue(text="secreted"),
        ),
    ],
)
def test_a_stored_value_reads_back_as_its_typed_member(
    kind: ConstraintKind, value: object, typed: object
) -> None:
    constraint = _constraint(kind, value)

    assert constraint.value == typed
    assert Constraint.model_validate(constraint.model_dump(by_alias=True)) == constraint


def test_a_value_of_another_kind_is_refused() -> None:
    with pytest.raises(ValidationError, match="a percentile value on a fold_change"):
        _constraint(
            ConstraintKind.FOLD_CHANGE, {"kind": "percentile", "end": "top", "share": 5}
        )


def test_a_requirement_stored_without_a_value_is_untyped() -> None:
    stored = Constraint.model_validate(
        {"kind": "percentile", "requestedValue": "top 10%", "label": "top 10%"}
    )

    assert stored.value is None


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "percentile", "end": "top", "share": 0},
        {"kind": "percentile", "end": "top", "share": 101},
        {"kind": "statistical_threshold", "atMost": 0},
        {"kind": "statistical_threshold", "atMost": 1.5},
        {"kind": "fold_change", "cut": 0, "scale": "fold"},
        {"kind": "data_type", "data": "chip_seq"},
        {"kind": "record_type", "recordClass": ""},
        {"kind": "record_type", "recordClass": "group", "role": "beside"},
    ],
)
def test_a_value_out_of_its_range_is_refused(value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _constraint(ConstraintKind(str(value["kind"])), value)


@pytest.mark.parametrize(
    ("record_class", "answering"),
    [
        ("gene", {"gene", "transcript", "sequence"}),
        ("transcript", {"transcript"}),
        ("group", {"group"}),
    ],
)
def test_a_record_class_is_answered_by_itself_and_by_the_gene_table(
    record_class: str, answering: set[str]
) -> None:
    assert RecordTypeValue(record_class=record_class).answering_classes == answering
