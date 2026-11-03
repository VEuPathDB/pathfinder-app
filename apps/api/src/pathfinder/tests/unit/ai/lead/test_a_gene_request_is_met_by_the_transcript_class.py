"""A request for genes is met by a strategy on the transcript class: the site
counts a transcript answer in genes. The check reads the class the site gives
the result step."""

from __future__ import annotations

from pathfinder.domain.requirement_checks import record_type_check
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    RecordTypeValue,
)


def _record_type(record_class: str | None) -> Constraint:
    return Constraint(
        kind=ConstraintKind.RECORD_TYPE,
        label="record type",
        requested_value="genes",
        source=ConstraintSource.USER_EXPLICIT,
        value=None
        if record_class is None
        else RecordTypeValue(record_class=record_class),
    )


def _checked(stated: Constraint, root_class: str) -> SiteCheck:
    return record_type_check(stated, root_class, {root_class})


def test_genes_is_met_by_the_transcript_class() -> None:
    check = _checked(_record_type("gene"), "transcript")

    assert (check.status, check.evidence) == (
        "pass",
        "the result step returns transcript records",
    )


def test_a_class_counted_in_another_noun_fails_the_stated_genes() -> None:
    check = _checked(_record_type("gene"), "snp")

    assert (check.status, check.evidence) == (
        "fail",
        "the result step returns snp records",
    )


def test_genes_is_met_by_orthomcls_protein_class() -> None:
    assert _checked(_record_type("gene"), "sequence").status == "pass"


def test_a_transcript_request_is_not_met_by_the_gene_class() -> None:
    assert _checked(_record_type("transcript"), "gene").status == "fail"


def test_a_record_type_with_no_typed_class_is_unchecked() -> None:
    check = _checked(_record_type(None), "transcript")

    assert (check.status, check.evidence, check.why_unchecked) == (
        "unchecked",
        "no typed record class to compare",
        "untyped",
    )
