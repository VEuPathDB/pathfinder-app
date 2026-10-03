"""The bound facts a constraint is grounded against, and whether the analysis
that states a cut is still to run."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import Field
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
    GroundedConstraint,
)
from pathfinder.domain.strategy.operational_spec import Criterion, SpecStructure

type AnalysisCut = Callable[[AnalysisBinding], float | None]


class RealizedSpec(CamelModel):
    """The bound facts a constraint is grounded against: the criteria's WDK
    search names, the union of their parameter names, the values bound to them,
    the tree the criteria are combined in, and the type of the upload each
    criterion runs on, by criterion id."""

    search_names: list[str] = Field(default_factory=list)
    param_names: frozenset[str] = Field(default_factory=frozenset)
    param_values: dict[str, str] = Field(default_factory=dict)
    structure: SpecStructure | None = None
    criteria: list[Criterion] = Field(default_factory=list)
    upload_types: dict[str, str] = Field(default_factory=dict)

    @property
    def realizes_nothing(self) -> bool:
        """Whether no criterion binds a search or holds an analysis yet."""
        return not self.search_names and not any(
            c.bound or c.analysis is not None for c in self.criteria
        )

    @property
    def analysis_pending(self) -> bool:
        """Whether a criterion waits for the analysis workflow to realize it."""
        return any(c.pending_analysis for c in self.criteria)

    def uncut(self, cut: AnalysisCut) -> bool:
        """Whether a compute the spec holds has no value for this cut."""
        return any(
            c.analysis is not None
            and c.analysis.method is not None
            and cut(c.analysis) is None
            for c in self.criteria
        )

    def awaits_analysis(self, cut: AnalysisCut) -> bool:
        """Whether an analysis that can state this cut has not run, or ran and
        holds no value for it."""
        return self.analysis_pending or self.uncut(cut)


def awaiting_analysis(c: Constraint) -> GroundedConstraint:
    """The constraint as provisional: the analysis that states it has not run."""
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.PROVISIONAL,
        note="the analysis that states it has not run",
    )
