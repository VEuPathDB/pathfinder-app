"""A check's requirement rows counted by status, against the counts a case states."""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.domain.evidence import RequirementCheck
from pathfinder.evals.case import ExpectedOutcome
from pathfinder.evals.difference import CaseDifference


class RequirementCounts(CamelModel):
    """How many of a check's requirement rows carry each status."""

    model_config = ConfigDict(frozen=True)

    met: int = 0
    unmet: int = 0
    unexpressed: int = 0
    unshown: int = 0
    unjudged: int = 0


def requirement_counts(rows: Sequence[RequirementCheck]) -> RequirementCounts:
    """The check's requirement rows, counted by the status a reader is shown."""
    statuses = [row.shown_status for row in rows]
    return RequirementCounts(
        met=statuses.count("met"),
        unmet=statuses.count("unmet"),
        unexpressed=statuses.count("unexpressed"),
        unshown=statuses.count("unshown"),
        unjudged=statuses.count("unjudged"),
    )


def requirement_differences(
    expected: ExpectedOutcome,
    counted: RequirementCounts | None,
) -> list[CaseDifference]:
    """The met and unmet rows the check reported, against the counts the case states."""
    compared = (
        (
            "metRequirements",
            expected.met_requirements,
            None if counted is None else counted.met,
        ),
        (
            "unmetRequirements",
            expected.unmet_requirements,
            None if counted is None else counted.unmet,
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


__all__ = ["RequirementCounts", "requirement_counts", "requirement_differences"]
