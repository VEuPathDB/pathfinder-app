from __future__ import annotations

from collections.abc import Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.domain.caveats import Gap
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.evals.case import ExpectedOutcome
from pathfinder.evals.difference import CaseDifference

_UNEXPRESSED = frozenset({"word", "requirement"})


class CheckCounts(CamelModel):
    model_config = ConfigDict(frozen=True)

    passed: int = 0
    failed: int = 0
    unchecked: int = 0
    unexpressed: int = 0


def check_counts(checks: Sequence[SiteCheck], gaps: Sequence[Gap]) -> CheckCounts:
    statuses = [check.status for check in checks]
    return CheckCounts(
        passed=statuses.count("pass"),
        failed=statuses.count("fail"),
        unchecked=statuses.count("unchecked"),
        unexpressed=sum(1 for gap in gaps if gap.kind in _UNEXPRESSED),
    )


def check_differences(
    expected: ExpectedOutcome, counted: CheckCounts | None
) -> list[CaseDifference]:
    compared = (
        (
            "passedChecks",
            expected.passed_checks,
            None if counted is None else counted.passed,
        ),
        (
            "failedChecks",
            expected.failed_checks,
            None if counted is None else counted.failed,
        ),
        (
            "unexpressedRequirements",
            expected.unexpressed_requirements,
            None if counted is None else counted.unexpressed,
        ),
    )
    return [
        CaseDifference(field=field, expected=str(want), actual=str(got))
        for field, want, got in compared
        if want is not None and want != got
    ]


__all__ = ["CheckCounts", "check_counts", "check_differences"]
