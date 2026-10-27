"""A request for genes is met by a strategy on the transcript class: the site
counts a transcript answer in genes. The check reads the class the site gives
the result step."""

from __future__ import annotations

import pytest

from pathfinder.domain.requirement_checks import classes_named, record_type_check
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.services.strategies.record_classes import record_names_of
from pathfinder.tests._support.organism_reads import TRANSCRIPT
from pathfinder.tests.unit.ai.lead.conftest import requirement


def _checked(stated: Constraint, root_class: str) -> SiteCheck:
    named = classes_named(stated.requested_value, record_names_of([TRANSCRIPT]))
    return record_type_check(stated, "answer", named, root_class, {root_class})


def _record_type(value: str) -> Constraint:
    return requirement(ConstraintKind.RECORD_TYPE, "record type", value)


@pytest.mark.parametrize("value", ["genes", "gene records", "transcripts"])
def test_genes_is_met_by_the_transcript_class(value: str) -> None:
    check = _checked(_record_type(value), "transcript")

    assert (check.status, check.evidence) == (
        "pass",
        "the result step returns transcript records",
    )


def test_a_class_counted_in_another_noun_fails_the_stated_genes() -> None:
    check = _checked(_record_type("genes"), "snp")

    assert (check.status, check.evidence) == (
        "fail",
        "the result step returns snp records",
    )


def test_genes_is_met_by_orthomcls_protein_class() -> None:
    assert _checked(_record_type("genes"), "sequence").status == "pass"


def test_a_class_the_site_does_not_name_is_unchecked() -> None:
    check = _checked(_record_type("pathways"), "transcript")

    assert (check.status, check.evidence) == (
        "unchecked",
        "the site names no record class by these words",
    )


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
