"""The verdict on one run when the case records a count: pass, re-measure or fail.

VEuPathDB data moves between site builds and a step layout does not. So a
changed layout, reply or gate fails on any build, and a root count off by more
than the tolerance on a new build asks for the count to be measured again.
"""

from __future__ import annotations

from typing import Literal

from pathfinder.evals.case import EvalCase
from pathfinder.evals.scoring import CaseDifference, ObservedOutcome, score_case

DriftVerdict = Literal["pass", "re-measure", "fail"]

_TOLERANCE_FLOOR = 5
_TOLERANCE_SHARE = 0.10


def _tolerance(count: int) -> float:
    """How far a count may move on a new build: 5 genes or 10 %, the larger."""
    return max(_TOLERANCE_FLOOR, _TOLERANCE_SHARE * count)


def count_difference(
    case: EvalCase,
    observed: ObservedOutcome,
    build_now: str,
) -> CaseDifference | None:
    """The recorded root count against the produced one, each with its build."""
    recorded = case.expected.root_count
    if recorded is None or observed.root_count == recorded.count:
        return None
    return CaseDifference(
        field="rootCount",
        expected=f"{recorded.count} (build {recorded.build})",
        actual=f"{observed.root_count} (build {build_now})",
    )


def classify(
    case: EvalCase,
    observed: ObservedOutcome,
    build_now: str,
) -> DriftVerdict:
    """Every difference but the count fails; the count alone drifts only on a new build."""
    if score_case(case, observed).differences:
        return "fail"
    recorded = case.expected.root_count
    if recorded is None or observed.root_count == recorded.count:
        return "pass"
    if observed.root_count is None or build_now == recorded.build:
        return "fail"
    if abs(observed.root_count - recorded.count) <= _tolerance(recorded.count):
        return "pass"
    return "re-measure"


__all__ = ["DriftVerdict", "classify", "count_difference"]
