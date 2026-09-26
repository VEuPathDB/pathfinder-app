"""A recorded count that moved is a re-measure, a pass or a failure, by build and size."""

from __future__ import annotations

import datetime

from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    RecordedCount,
)
from pathfinder.evals.drift import classify, count_difference
from pathfinder.evals.scoring import CaseDifference, ObservedOutcome

_INTERSECT = "(GenesWithSignalPeptide INTERSECT GenesByTransmembraneDomains)"
_UNION = "(GenesWithSignalPeptide UNION GenesByTransmembraneDomains)"


def _case(*, count: int | None = 116) -> EvalCase:
    return EvalCase(
        name="uat-s2-plasmodb",
        turns=["Find the genes."],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the intersect and its count",
        expected=ExpectedOutcome(
            builds_strategy=True,
            structure=_INTERSECT,
            root_count=(
                None
                if count is None
                else RecordedCount(
                    count=count, build="71", measured_on=datetime.date(2026, 9, 24)
                )
            ),
        ),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="uat/flows-strategy-standard.md#s2",
            added_at="2026-09-25",
        ),
    )


def _observed(count: int | None, *, structure: str = _INTERSECT) -> ObservedOutcome:
    return ObservedOutcome(built_strategy=True, structure=structure, root_count=count)


def test_the_recorded_count_on_the_recorded_build_passes() -> None:
    assert classify(_case(), _observed(116), build_now="71") == "pass"


def test_a_count_off_on_the_same_build_fails() -> None:
    assert classify(_case(), _observed(117), build_now="71") == "fail"


def test_a_count_within_the_tolerance_on_a_new_build_passes() -> None:
    verdicts = [
        classify(_case(), _observed(count), build_now="72") for count in (105, 127)
    ]

    assert verdicts == ["pass", "pass"]


def test_a_count_outside_the_tolerance_on_a_new_build_asks_for_a_re_measure() -> None:
    verdicts = [
        classify(_case(), _observed(count), build_now="72") for count in (104, 128)
    ]

    assert verdicts == ["re-measure", "re-measure"]


def test_a_small_count_takes_the_five_gene_floor() -> None:
    verdicts = [
        classify(_case(count=25), _observed(count), build_now="72")
        for count in (20, 30, 31)
    ]

    assert verdicts == ["pass", "pass", "re-measure"]


def test_a_changed_tree_fails_whatever_the_count_does() -> None:
    changed = _observed(1203, structure=_UNION)

    assert classify(_case(), changed, build_now="72") == "fail"


def test_a_changed_tree_with_the_count_off_on_a_new_build_fails() -> None:
    changed = _observed(120, structure=_UNION)

    assert classify(_case(), changed, build_now="72") == "fail"


def test_a_missing_count_fails_on_any_build() -> None:
    assert classify(_case(), _observed(None), build_now="72") == "fail"


def test_a_case_that_records_no_count_is_judged_on_its_structure() -> None:
    assert classify(_case(count=None), _observed(9000), build_now="72") == "pass"


def test_a_count_off_is_reported_with_both_builds() -> None:
    assert count_difference(_case(), _observed(130), build_now="72") == (
        CaseDifference(
            field="rootCount",
            expected="116 (build 71)",
            actual="130 (build 72)",
        )
    )


def test_an_equal_count_reports_no_difference_on_any_build() -> None:
    differences = [
        count_difference(_case(), _observed(116), build_now=build)
        for build in ("71", "72")
    ]

    assert differences == [None, None]
