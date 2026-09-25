"""A case reads the requirement rows the check reported: how many the strategy
met and how many it left unmet."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.evidence import RequirementCheck
from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome
from pathfinder.evals.extract import EvalExtract, ExtractedVerification
from pathfinder.evals.scoring import (
    ObservedOutcome,
    RequirementCounts,
    requirement_counts,
    score_case,
)

_MET = RequirementCheck(
    text="with a signal peptide",
    turn=1,
    answered_by=["s1"],
    how="search",
    status="met",
)
_UNMET = RequirementCheck(
    text="at least 2 transmembrane domains", turn=1, how="search", status="unmet"
)
_UNEXPRESSED = RequirementCheck(
    text="orthologs", turn=2, how="search", status="unexpressed"
)


def _case(*, met: int | None, unmet: int | None) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["P. falciparum 3D7 genes with a signal peptide"],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the requirement rows",
        expected=ExpectedOutcome(
            builds_strategy=True, met_requirements=met, unmet_requirements=unmet
        ),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-09-24",
        ),
    )


def test_the_rows_are_counted_by_status() -> None:
    counts = requirement_counts([_MET, _UNMET, _UNEXPRESSED, _MET])

    assert counts == RequirementCounts(met=2, unmet=1, unexpressed=1)


def test_a_run_whose_rows_disagree_is_named_on_each_count() -> None:
    observed = ObservedOutcome(
        built_strategy=True, requirements=requirement_counts([_MET, _UNMET])
    )

    score = score_case(_case(met=2, unmet=0), observed)

    assert [(d.field, d.expected, d.actual) for d in score.differences] == [
        ("metRequirements", "2", "1"),
        ("unmetRequirements", "0", "1"),
    ]


def test_a_run_no_check_judged_has_no_rows_to_count() -> None:
    score = score_case(_case(met=1, unmet=None), ObservedOutcome(built_strategy=True))

    assert [(d.field, d.actual) for d in score.differences] == [
        ("metRequirements", "None")
    ]


def test_an_extract_refuses_an_email_in_a_requirement() -> None:
    row = _MET.model_copy(update={"text": "as ada@example.org asked"})

    with pytest.raises(ValidationError, match="email"):
        EvalExtract(
            site_id="plasmodb",
            assistant_id="pathfinder",
            verification=ExtractedVerification(success=True, requirements=[row]),
        )
