"""The run summary: the numbers a trend is drawn from."""

from __future__ import annotations

from pathfinder.evals.difference import CaseDifference
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
    assert payload["refusals"] == 0
    assert payload["cases"][0]["differences"][0]["field"] == "structure"
    assert payload["cases"][0]["refusedTools"] == []


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


def test_the_refused_tools_round_trip_and_sum_into_the_run() -> None:
    summary = _summary(
        CaseResult(
            name="a",
            verdict="pass",
            refused_tools=["classify_user_intent", "read_gene_record"],
        ),
        CaseResult(name="b", verdict="fail", refused_tools=["get_strategy"]),
    )

    payload = summary.model_dump(by_alias=True, mode="json")
    restored = EvalRunSummary.model_validate(payload)

    assert payload["refusals"] == 3
    assert payload["cases"][0]["refusedTools"] == [
        "classify_user_intent",
        "read_gene_record",
    ]
    assert restored.cases == summary.cases


def test_a_case_not_run_counts_as_neither_passed_nor_failed_nor_run() -> None:
    summary = _summary(
        CaseResult(name="a", verdict="pass"),
        CaseResult(name="b", verdict="fail"),
        CaseResult(
            name="c",
            verdict="not-run",
            error="cryptodb login did not answer (connect timeout)",
        ),
    )

    counted = (summary.passed, summary.failed, summary.errored, summary.not_run)
    assert counted == (1, 1, 0, 1)
    assert summary.case_count == 3
    assert summary.pass_rate == 0.5
    assert summary.model_dump(by_alias=True, mode="json")["notRun"] == 1
