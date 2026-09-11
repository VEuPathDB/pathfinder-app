"""The machine-readable result of one eval run: the logic layer's SLI feed.

The shape is ours, not the harness's, so a change of harness does not change
the feed. It answers one question per case and one per run: did this change
make the assistant worse at a real task.
"""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field

from pathfinder.evals.distance import StrategyDistance
from pathfinder.evals.scoring import CaseDifference


class CaseResult(CamelModel):
    """One case's verdict, the differences behind it, and how far off it is.

    The distance is carried on a pass too: a trend is drawn from how far a run
    moved, not only from whether it crossed the line.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    differences: list[CaseDifference] = Field(default_factory=list)
    distance: StrategyDistance | None = None
    error: str = ""
    duration_seconds: float = 0.0


class EvalRunSummary(CamelModel):
    """Every case of one run, plus the numbers a trend is drawn from."""

    model_config = ConfigDict(frozen=True)

    harness: str
    provider: str
    assistant_id: str
    ran_at: str
    cases: list[CaseResult] = Field(default_factory=list)

    @computed
    def case_count(self) -> int:
        return len(self.cases)

    @computed
    def passed(self) -> int:
        return _passed(self.cases)

    @computed
    def failed(self) -> int:
        return sum(1 for case in self.cases if not case.passed and not case.error)

    @computed
    def errored(self) -> int:
        return sum(1 for case in self.cases if case.error)

    @computed
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return round(_passed(self.cases) / len(self.cases), 4)


def _passed(cases: list[CaseResult]) -> int:
    return sum(1 for case in cases if case.passed and not case.error)


__all__ = ["CaseResult", "EvalRunSummary"]
