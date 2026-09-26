"""The run summary: the numbers a trend is drawn from."""

from __future__ import annotations

from pathfinder.evals.scoring import CaseDifference
from pathfinder.evals.summary import CaseResult, EvalRunSummary


def _summary(*cases: CaseResult) -> EvalRunSummary:
    return EvalRunSummary(
        harness="pydantic-evals",
        provider="mock",
        assistant_id="pathfinder",
        ran_at="2026-08-23T00:00:00+00:00",
        cases=list(cases),
    )


def test_an_empty_run_reports_a_zero_pass_rate() -> None:
    summary = _summary()

    assert summary.case_count == 0
    assert summary.pass_rate == 0.0


def test_a_green_run_reports_one() -> None:
    summary = _summary(
        CaseResult(name="a", verdict="pass"),
        CaseResult(name="b", verdict="pass"),
    )

    assert summary.passed == 2
    assert summary.failed == 0
    assert summary.pass_rate == 1.0


def test_an_errored_case_counts_as_neither_passed_nor_failed() -> None:
    summary = _summary(
        CaseResult(name="a", verdict="pass"),
        CaseResult(name="b", verdict="fail", error="boom"),
    )

    assert summary.passed == 1
    assert summary.failed == 0
    assert summary.errored == 1
    assert summary.case_count == 2
    assert summary.pass_rate == 0.5


def test_the_serialized_summary_carries_the_counts_and_the_differences() -> None:
    summary = _summary(
        CaseResult(
            name="a",
            verdict="fail",
            differences=[
                CaseDifference(field="structure", expected="x", actual="y"),
            ],
        ),
    )

    payload = summary.model_dump(by_alias=True, mode="json")

    assert payload["passRate"] == 0.0
    assert payload["caseCount"] == 1
    assert payload["cases"][0]["differences"][0]["field"] == "structure"


def test_a_re_measure_counts_as_neither_passed_nor_failed() -> None:
    summary = _summary(
        CaseResult(name="a", verdict="pass", observed_count=116),
        CaseResult(name="b", verdict="re-measure", observed_count=140),
        CaseResult(name="c", verdict="fail", observed_count=None),
    )

    counted = (summary.passed, summary.re_measure, summary.failed, summary.errored)
    assert counted == (1, 1, 1, 0)
    assert [case.passed for case in summary.cases] == [True, False, False]


def test_the_serialized_case_carries_its_verdict_and_its_count() -> None:
    summary = _summary(CaseResult(name="a", verdict="re-measure", observed_count=140))

    payload = summary.model_dump(by_alias=True, mode="json")

    assert payload["reMeasure"] == 1
    assert {
        key: payload["cases"][0][key] for key in ("verdict", "observedCount", "passed")
    } == {"verdict": "re-measure", "observedCount": 140, "passed": False}
