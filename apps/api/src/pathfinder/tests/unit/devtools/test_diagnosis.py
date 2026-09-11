from __future__ import annotations

from assistant_core.platform.types import JSONObject

from pathfinder.devtools.diagnosis import diagnose
from pathfinder.devtools.models import (
    CapturedToolCall,
    DecodedError,
    RunSummary,
    ToolStatus,
)


def _failed(seq: int, tool: str, errors: list[DecodedError]) -> CapturedToolCall:
    return CapturedToolCall(
        seq=seq,
        phase="planning",
        tool=tool,
        tool_call_id=f"c{seq}",
        status="failed",
        errors=errors,
        result="boom",
    )


def _call(
    seq: int,
    tool: str,
    status: ToolStatus,
    *,
    args: JSONObject | None = None,
    result: str | None = None,
    phase: str = "discovery",
) -> CapturedToolCall:
    return CapturedToolCall(
        seq=seq,
        phase=phase,
        tool=tool,
        tool_call_id=f"c{seq}",
        status=status,
        args=args,
        result=result,
    )


def test_detects_validation_catch22_on_same_param() -> None:
    calls = [
        _failed(
            1,
            "create_plan",
            [
                DecodedError(
                    kind="missing_required",
                    search_name="GenesByText",
                    param="document_type",
                ),
            ],
        ),
        _failed(
            2,
            "create_plan",
            [
                DecodedError(
                    kind="unknown_param",
                    search_name="GenesByText",
                    param="document_type",
                ),
            ],
        ),
    ]
    anomalies = diagnose(calls, {}, RunSummary())
    catch22 = [a for a in anomalies if a.kind == "validation_catch_22"]
    assert len(catch22) == 1
    assert "document_type" in catch22[0].message
    assert catch22[0].severity == "critical"
    assert any("create_plan" in e for e in catch22[0].evidence)


def test_detects_loop_on_repeated_tool_failures() -> None:
    calls = [_failed(i, "create_plan", []) for i in range(1, 7)]
    anomalies = diagnose(calls, {}, RunSummary())
    loops = [a for a in anomalies if a.kind == "loop"]
    assert loops
    assert "create_plan" in loops[0].message
    assert loops[0].details["guard_refusals"] == 0


def test_the_loop_says_when_the_repetition_guard_refused_the_call() -> None:
    """A guard refusal is a measured loop, so one is enough to report it."""
    calls = [
        _call(1, "get_strategy", "completed", result="{}"),
        _call(
            2,
            "get_strategy",
            "failed",
            result=(
                "You have called get_strategy 3 times with identical arguments "
                "and no intervening state change."
            ),
        ),
    ]

    anomalies = diagnose(calls, {}, RunSummary())

    loops = [a for a in anomalies if a.kind == "loop"]
    assert len(loops) == 1
    assert "repetition guard refused 1 identical call" in loops[0].message
    assert loops[0].details["guard_refusals"] == 1
    assert loops[0].evidence == ["tools/02-get_strategy.json"]


def test_detects_silent_zero_from_ledger() -> None:
    ledgers = {"execution": {"build": {"zeroResultSteps": ["s1", "s3"]}}}
    anomalies = diagnose([], ledgers, RunSummary())
    zeros = [a for a in anomalies if a.kind == "silent_zero"]
    assert zeros
    assert "s1" in zeros[0].message or "s1" in str(zeros[0].details)


def test_detects_no_plan_terminal() -> None:
    summary = RunSummary(
        status="error", terminal_error="Planning sub-agent returned no plan."
    )
    anomalies = diagnose([], {}, summary)
    assert any(a.kind == "no_plan" for a in anomalies)


_SERVICE_ERR = (
    "Transient error in get_search_overview: VEuPathDB service error: Request "
    "failed after retries: Server error '500 Internal Server Error' for url "
    "'https://vectorbase.org/.../GenesByRNASeqFoo?expandParams=true'. The service "
    "may be temporarily unavailable. Retrying."
)


def test_detects_repeated_wdk_service_error_on_same_search() -> None:
    calls = [
        _call(
            i,
            "get_search_overview",
            "failed",
            args={"search_name": "GenesByRNASeqFoo"},
            result=_SERVICE_ERR,
        )
        for i in range(1, 4)
    ]
    anomalies = diagnose(calls, {}, RunSummary())
    svc = [a for a in anomalies if a.kind == "wdk_service_error"]
    assert len(svc) == 1
    assert "GenesByRNASeqFoo" in svc[0].message
    assert svc[0].details["count"] == 3
    assert all("get_search_overview" in e for e in svc[0].evidence)


def test_breaker_handled_outage_not_counted_as_retry() -> None:
    directive = (
        "ERROR: SEARCH_UNAVAILABLE\nTOOL: get_search_overview\n"
        "'GenesByRNASeqFoo' returned repeated server errors and is persistently "
        "unavailable: VEuPathDB service error: Server error '500 Internal Server "
        "Error'. Do not call get_search_overview on it again."
    )
    calls = [
        _call(
            i,
            "get_search_overview",
            "failed",
            args={"search_name": "GenesByRNASeqFoo"},
            result=directive,
        )
        for i in range(1, 4)
    ]
    anomalies = diagnose(calls, {}, RunSummary())
    assert not [a for a in anomalies if a.kind == "wdk_service_error"]


def test_single_service_error_below_threshold_not_flagged() -> None:
    calls = [
        _call(
            1,
            "get_search_overview",
            "failed",
            args={"search_name": "GenesByRNASeqFoo"},
            result=_SERVICE_ERR,
        )
    ]
    anomalies = diagnose(calls, {}, RunSummary())
    assert not [a for a in anomalies if a.kind == "wdk_service_error"]


def test_detects_silent_constraint_violation() -> None:
    ledgers = {
        "verification": {
            "constraints": {
                "blocking": True,
                "unmetCount": 1,
                "grounded": [
                    {
                        "constraint": {
                            "kind": "data_type",
                            "requestedValue": "RNA-Seq",
                            "label": "data type",
                            "source": "user_explicit",
                        },
                        "status": "substituted",
                        "realizedValue": "microarray",
                        "note": "x",
                    }
                ],
            }
        }
    }
    anomalies = diagnose([], ledgers, RunSummary(status="ok"))
    hits = [a for a in anomalies if a.kind == "silent_constraint_violation"]
    assert len(hits) == 1
    assert "data type" in hits[0].message


def test_no_silent_constraint_violation_when_not_blocking() -> None:
    ledgers = {
        "verification": {
            "constraints": {"blocking": False, "unmetCount": 0, "grounded": []}
        }
    }
    anomalies = diagnose([], ledgers, RunSummary(status="ok"))
    assert not [a for a in anomalies if a.kind == "silent_constraint_violation"]


def test_clean_run_has_no_anomalies() -> None:
    calls = [
        CapturedToolCall(
            seq=1, phase="planning", tool="create_plan", status="completed"
        ),
    ]
    summary = RunSummary(status="ok", tokens=20000)
    assert diagnose(calls, {}, summary) == []


_SUBSTITUTED_LEDGER = {
    "verification": {
        "constraints": {
            "blocking": True,
            "unmetCount": 1,
            "grounded": [
                {
                    "constraint": {
                        "kind": "data_type",
                        "requestedValue": "RNA-Seq",
                        "label": "data type",
                        "source": "user_explicit",
                    },
                    "status": "substituted",
                    "realizedValue": "microarray",
                    "note": "x",
                }
            ],
        }
    }
}


class TestConstraintHandledInProse:
    """The anomaly's claim is that the turn never told the user. Prose is
    where a Lead usually tells them, so the detector has to read it."""

    def test_silent_when_the_reply_never_mentions_it(self) -> None:
        anomalies = diagnose(
            [],
            _SUBSTITUTED_LEDGER,
            RunSummary(status="ok"),
            assistant_text="Here are the 132 genes you asked for.",
        )
        assert [a for a in anomalies if a.kind == "silent_constraint_violation"]

    def test_not_silent_when_the_reply_names_the_constraint(self) -> None:
        anomalies = diagnose(
            [],
            _SUBSTITUTED_LEDGER,
            RunSummary(status="ok"),
            assistant_text=(
                "Note: no RNA-Seq dataset covers this, so I used a microarray "
                "one instead. The data type you asked for was not available."
            ),
        )
        assert not [a for a in anomalies if a.kind == "silent_constraint_violation"]

    def test_absent_prose_is_still_silent(self) -> None:
        # A run captured with no reply text must not be quietly excused.
        anomalies = diagnose([], _SUBSTITUTED_LEDGER, RunSummary(status="ok"))
        assert [a for a in anomalies if a.kind == "silent_constraint_violation"]


class TestZeroHandledInProse:
    def test_silent_when_the_reply_never_mentions_zero(self) -> None:
        anomalies = diagnose(
            [],
            {"execution": {"build": {"zeroResultSteps": ["s1"]}}},
            RunSummary(),
            assistant_text="Your strategy is ready.",
        )
        assert [a for a in anomalies if a.kind == "silent_zero"]

    def test_not_silent_when_the_reply_reports_the_empty_result(self) -> None:
        anomalies = diagnose(
            [],
            {"execution": {"build": {"zeroResultSteps": ["s1"]}}},
            RunSummary(),
            assistant_text=(
                "That intersection returned 0 genes, so there is no overlap "
                "between the two sets."
            ),
        )
        assert not [a for a in anomalies if a.kind == "silent_zero"]

    def test_a_reply_naming_the_step_also_counts(self) -> None:
        anomalies = diagnose(
            [],
            {"execution": {"build": {"zeroResultSteps": ["s1"]}}},
            RunSummary(),
            assistant_text="Step s1 came back empty.",
        )
        assert not [a for a in anomalies if a.kind == "silent_zero"]
