from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.caveats import RequirementGap, WordGap
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome, GatePlan
from pathfinder.evals.check_counts import CheckCounts, check_counts
from pathfinder.evals.extract import EvalExtract, ExtractedVerification
from pathfinder.evals.scoring import ObservedOutcome, score_case

_PASSED = SiteCheck(
    kind="result_count",
    subject="the strategy on the site",
    status="pass",
    evidence="the result step 11 ('Signal') holds 840 records",
)
_FAILED = SiteCheck(
    kind=ConstraintKind.ORGANISM,
    subject="Plasmodium falciparum 3D7",
    status="fail",
    evidence=(
        "21 of the 840 records of step 11 ('Signal') hold organisms the strategy "
        "does not select: Plasmodium falciparum IT (21)"
    ),
    requirement="organism:Plasmodium falciparum 3D7",
)
_UNCHECKED = _PASSED.model_copy(
    update={"kind": "step_valid", "status": "unchecked", "evidence": "no answer"}
)


def _case(*, passed: int | None, failed: int | None) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["P. falciparum 3D7 genes with a signal peptide"],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the checks on the site",
        expected=ExpectedOutcome(
            builds_strategy=True, passed_checks=passed, failed_checks=failed
        ),
        gates=GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-09-24",
        ),
    )


def test_the_checks_are_counted_by_status_and_the_gaps_no_search_states() -> None:
    counts = check_counts(
        [_PASSED, _FAILED, _UNCHECKED, _PASSED],
        [WordGap(word="exported"), RequirementGap(text="secreted")],
    )

    assert counts == CheckCounts(passed=2, failed=1, unchecked=1, unexpressed=2)


def test_a_run_whose_checks_disagree_is_named_on_each_count() -> None:
    observed = ObservedOutcome(
        built_strategy=True, checks=check_counts([_PASSED, _FAILED], [])
    )

    score = score_case(_case(passed=2, failed=0), observed)

    assert [(d.field, d.expected, d.actual) for d in score.differences] == [
        ("passedChecks", "2", "1"),
        ("failedChecks", "0", "1"),
    ]


def test_a_run_no_check_judged_has_no_checks_to_count() -> None:
    score = score_case(
        _case(passed=1, failed=None), ObservedOutcome(built_strategy=True)
    )

    assert [(d.field, d.actual) for d in score.differences] == [
        ("passedChecks", "None")
    ]


def test_an_extract_refuses_an_email_in_a_check() -> None:
    check = _FAILED.model_copy(update={"subject": "as ada@example.org asked"})

    with pytest.raises(ValidationError, match="email"):
        EvalExtract(
            site_id="plasmodb",
            assistant_id="pathfinder",
            verification=ExtractedVerification(success=True, checks=[check]),
        )
