from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from assistant_core.capabilities.repetition_guard import (
    CALL_CAP_MARKER,
    REPETITION_MARKER,
)

from pathfinder.devtools.models import (
    Anomaly,
    CapturedToolCall,
    GroundedConstraintProbe,
    LedgerConstraintsProbe,
    LedgerProbe,
    RunSummary,
    SearchArgs,
)

LOOP_THRESHOLD = 5
BUDGET_WARN_TOKENS = 200_000
SERVICE_ERROR_THRESHOLD = 2

_SERVICE_ERROR_RE = re.compile(
    r"5\d\d (?:internal server error|server error)|server error '5|"
    r"temporarily unavailable",
    re.IGNORECASE,
)
_ZERO_RESULT_RE = re.compile(
    r"\b(?:0|no|zero|none|empty)\b[^.]{0,40}?"
    r"\b(?:gene|transcript|result|record|hit|row|overlap|match)|"
    r"\b(?:returned|came back|yielded|found)\b[^.]{0,20}?"
    r"\b(?:0|no|zero|nothing|empty)\b",
    re.IGNORECASE,
)


def _evidence(calls: list[CapturedToolCall]) -> list[str]:
    return [f"tools/{c.seq:02d}-{c.tool}.json" for c in calls]


def _catch_22(calls: list[CapturedToolCall]) -> list[Anomaly]:
    missing: dict[tuple[str | None, str | None], list[CapturedToolCall]] = defaultdict(
        list
    )
    unknown: dict[tuple[str | None, str | None], list[CapturedToolCall]] = defaultdict(
        list
    )
    for call in calls:
        for err in call.errors:
            key = (err.search_name, err.param)
            if err.kind == "missing_required":
                missing[key].append(call)
            elif err.kind == "unknown_param":
                unknown[key].append(call)
    out: list[Anomaly] = []
    for key in sorted(
        set(missing) & set(unknown), key=lambda k: (k[0] or "", k[1] or "")
    ):
        search, param = key
        evidence_calls = missing[key] + unknown[key]
        where = f" on {search!r}" if search else ""
        out.append(
            Anomaly(
                kind="validation_catch_22",
                severity="critical",
                message=(
                    f"Parameter {param!r}{where} is required by one validator but "
                    f"rejected as unknown by another - unsatisfiable. The planner "
                    f"cannot produce any value that passes both."
                ),
                evidence=_evidence(evidence_calls),
                details={"param": param, "search_name": search},
            )
        )
    return out


def _guard_refused(call: CapturedToolCall) -> bool:
    """Did the repetition guard produce this call's result?"""
    if call.result is None:
        return False
    return REPETITION_MARKER in call.result or CALL_CAP_MARKER in call.result


def refused(call: CapturedToolCall) -> bool:
    """The call came back as a retry prompt, or as the repetition guard's text."""
    return call.status == "failed" or _guard_refused(call)


def _failure_streak(calls: list[CapturedToolCall]) -> list[CapturedToolCall]:
    """The longest run of failures no completed call interrupts."""
    longest: list[CapturedToolCall] = []
    streak: list[CapturedToolCall] = []
    for call in calls:
        if call.status == "failed":
            streak = [*streak, call]
            longest = max(longest, streak, key=len)
        elif call.status == "completed":
            streak = []
    return longest


def _identical_completions(calls: list[CapturedToolCall]) -> list[CapturedToolCall]:
    """The completed calls whose arguments an earlier completed call already sent."""
    seen: set[str] = set()
    repeats: list[CapturedToolCall] = []
    for call in calls:
        if call.status != "completed" or _guard_refused(call):
            continue
        key = json.dumps(call.args, sort_keys=True, default=str)
        if key in seen:
            repeats.append(call)
        seen.add(key)
    return repeats


def _tool_loop(tool: str, calls: list[CapturedToolCall]) -> Anomaly | None:
    failed = _failure_streak(calls)
    repeats = _identical_completions(calls)
    guarded = [c for c in calls if _guard_refused(c)]
    parts: list[str] = []
    if len(failed) >= LOOP_THRESHOLD:
        signatures = {(e.kind, e.param) for c in failed for e in c.errors}
        parts.append(
            f"{tool} failed {len(failed)} times in a row "
            f"({len(signatures) or 'unclassified'} distinct error signatures) "
            f"- the agent is stuck retrying."
        )
    if len(repeats) >= LOOP_THRESHOLD:
        parts.append(
            f"{tool} completed {len(repeats)} calls whose arguments an earlier "
            f"call already sent - the agent re-reads what it holds."
        )
    if guarded:
        parts.append(
            f"The repetition guard refused {len(guarded)} identical call(s) of {tool}."
        )
    if not parts:
        return None
    seen = {c.seq: c for c in failed + repeats + guarded}
    return Anomaly(
        kind="loop",
        severity="critical",
        message=" ".join(parts),
        evidence=_evidence([seen[key] for key in sorted(seen)]),
        details={
            "tool": tool,
            "failures": len(failed),
            "identical_completions": len(repeats),
            "guard_refusals": len(guarded),
        },
    )


def loops(calls: list[CapturedToolCall]) -> list[Anomaly]:
    """One loop per tool that failed in a row, repeated a completed read, or
    met the repetition guard, at ``LOOP_THRESHOLD`` calls or one guard refusal."""
    by_tool: dict[str, list[CapturedToolCall]] = defaultdict(list)
    for call in calls:
        by_tool[call.tool].append(call)
    return [
        anomaly
        for tool in sorted(by_tool)
        if (anomaly := _tool_loop(tool, by_tool[tool])) is not None
    ]


def _wdk_service_errors(calls: list[CapturedToolCall]) -> list[Anomaly]:
    by_search: dict[tuple[str, str | None], list[CapturedToolCall]] = defaultdict(list)
    for call in calls:
        if call.status != "failed" or not call.result:
            continue
        if "SEARCH_UNAVAILABLE" in call.result:
            continue
        if not _SERVICE_ERROR_RE.search(call.result):
            continue
        search = SearchArgs.model_validate(call.args or {}).search_name
        by_search[(call.tool, search)].append(call)
    out: list[Anomaly] = []
    for (tool, search), hits in sorted(
        by_search.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")
    ):
        if len(hits) < SERVICE_ERROR_THRESHOLD:
            continue
        where = f" on {search!r}" if search else ""
        out.append(
            Anomaly(
                kind="wdk_service_error",
                severity="warning",
                message=(
                    f"{tool} hit a WDK server error (5xx){where} {len(hits)} times "
                    f"- the agent retried an unavailable search instead of routing "
                    f"around it. Likely an upstream outage, not a PathFinder bug."
                ),
                evidence=_evidence(hits),
                details={"tool": tool, "search_name": search, "count": len(hits)},
            )
        )
    return out


def _mentions(text: str, needle: str) -> bool:
    """Does the reply refer to this label or id, ignoring case and separators?"""
    flat = re.sub(r"[\W_]+", " ", text).casefold()
    target = re.sub(r"[\W_]+", " ", needle).casefold().strip()
    return bool(target) and target in flat


def _stated(
    probe: LedgerConstraintsProbe, status: str
) -> list[GroundedConstraintProbe]:
    """The researcher's own constraints the grounding left at this status."""
    return [
        g
        for g in probe.grounded
        if g.constraint.source == "user_explicit" and g.status == status
    ]


def _constraints_by_phase(
    ledgers: dict[str, dict[str, Any]],
) -> list[tuple[str, LedgerConstraintsProbe]]:
    read = [
        (phase, LedgerProbe.model_validate(ledger)) for phase, ledger in ledgers.items()
    ]
    return [(phase, probe.constraints) for phase, probe in read if probe.constraints]


def _silent_constraint_violation(
    ledgers: dict[str, dict[str, Any]],
    assistant_text: str,
) -> list[Anomaly]:
    out: list[Anomaly] = []
    for phase, probe in _constraints_by_phase(ledgers):
        substituted = [g for g in _stated(probe, "substituted") if g.constraint.hard]
        # A Lead that explained the substitution in its reply was not silent.
        spoken = [
            value
            for g in substituted
            for value in (g.constraint.label, g.constraint.requested_value)
            if value and _mentions(assistant_text, value)
        ]
        if not substituted or spoken:
            continue
        labels = [g.constraint.label for g in substituted]
        out.append(
            Anomaly(
                kind="silent_constraint_violation",
                severity="critical",
                message=(
                    f"{len(substituted)} user-explicit constraint(s) unmet "
                    f"({', '.join(labels)}) yet the turn did not pause "
                    f"or flag it - the plan silently deviated from what the user asked."
                ),
                evidence=[f"state/{phase}.json"],
                details={
                    "phase": phase,
                    "unmet_count": len(substituted),
                    "labels": labels,
                },
            )
        )
    return out


def _ungroundable_constraints(ledgers: dict[str, dict[str, Any]]) -> list[Anomaly]:
    out: list[Anomaly] = []
    for phase, probe in _constraints_by_phase(ledgers):
        unread = _stated(probe, "ungroundable")
        if not unread:
            continue
        read_as = "; ".join(f"{g.constraint.label}: {g.note}" for g in unread)
        out.append(
            Anomaly(
                kind="ungroundable_constraint",
                severity="warning",
                message=(
                    f"{len(unread)} user-explicit constraint(s) could not be read "
                    f"against the strategy ({read_as}) - whether the strategy "
                    f"meets them is not known."
                ),
                evidence=[f"state/{phase}.json"],
                details={
                    "phase": phase,
                    "labels": [g.constraint.label for g in unread],
                    "notes": [g.note for g in unread],
                },
            )
        )
    return out


def _silent_zero(
    ledgers: dict[str, dict[str, Any]],
    assistant_text: str,
) -> list[Anomaly]:
    out: list[Anomaly] = []
    for phase, ledger in ledgers.items():
        zero_steps = ((ledger or {}).get("build") or {}).get("zeroResultSteps") or []
        reported = _ZERO_RESULT_RE.search(assistant_text) is not None or any(
            _mentions(assistant_text, str(step)) for step in zero_steps
        )
        if zero_steps and not reported:
            out.append(
                Anomaly(
                    kind="silent_zero",
                    severity="warning",
                    message=(
                        f"{len(zero_steps)} step(s) returned 0 results in {phase} "
                        f"({', '.join(map(str, zero_steps))}) - possible silent failure "
                        f"(e.g. missing JSESSIONID, wrong params)."
                    ),
                    evidence=[f"state/{phase}.json"],
                    details={"phase": phase, "zero_result_steps": zero_steps},
                )
            )
    return out


def _budget(summary: RunSummary) -> list[Anomaly]:
    if summary.tokens < BUDGET_WARN_TOKENS:
        return []
    severity = "critical" if summary.status == "error" else "warning"
    return [
        Anomaly(
            kind="budget_burn",
            severity=severity,
            message=(
                f"Turn consumed {summary.tokens} tokens (${summary.cost_usd:.2f}) "
                f"with status={summary.status} - abnormally high."
            ),
            evidence=["summary.json"],
            details={"tokens": summary.tokens, "cost_usd": summary.cost_usd},
        )
    ]


def _no_plan(summary: RunSummary) -> list[Anomaly]:
    if summary.terminal_error and "no plan" in summary.terminal_error.lower():
        return [
            Anomaly(
                kind="no_plan",
                severity="critical",
                message=f"Planning terminated without a plan: {summary.terminal_error}",
                evidence=["summary.json", "state/planning.json"],
                details={"terminal_error": summary.terminal_error},
            )
        ]
    return []


def diagnose(
    calls: list[CapturedToolCall],
    ledgers: dict[str, dict[str, Any]],
    summary: RunSummary,
    assistant_text: str = "",
) -> list[Anomaly]:
    """Run every fingerprint detector over a captured run and return the
    anomalies found, most severe first. Pure; never raises.

    ``assistant_text`` is the reply the user actually saw. The ``silent_*``
    detectors need it: their claim is that the turn never surfaced the
    problem, and prose is where a Lead usually surfaces it. Omitting it means
    "nothing was said", which keeps an uncaptured run honest rather than
    excused."""

    anomalies = (
        _catch_22(calls)
        + loops(calls)
        + _wdk_service_errors(calls)
        + _silent_constraint_violation(ledgers, assistant_text)
        + _ungroundable_constraints(ledgers)
        + _silent_zero(ledgers, assistant_text)
        + _budget(summary)
        + _no_plan(summary)
    )
    rank = {"critical": 0, "warning": 1, "info": 2}
    return sorted(anomalies, key=lambda a: rank.get(a.severity, 3))
