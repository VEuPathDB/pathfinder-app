from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from veupathdb.domain.parameters import to_wire

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
)
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.realized_spec import (
    AnalysisCut,
    RealizedSpec,
    awaiting_analysis,
)

COMPARED_THROUGH_A_LINK = frozenset(
    {
        ConstraintKind.PERCENTILE,
        ConstraintKind.FOLD_CHANGE,
        ConstraintKind.STATISTICAL_THRESHOLD,
    }
)
NO_LINK = "no criterion links it to a parameter"


class LinkedParam(NamedTuple):
    name: str
    wire: str
    display_name: str

    @property
    def number(self) -> float | None:
        try:
            return float(self.wire)
        except ValueError:
            return None


def linking(c: Constraint, criteria: Sequence[Criterion]) -> list[Criterion]:
    return [k for k in criteria if k.links(c.id)]


def linked_params(c: Constraint, criteria: Sequence[Criterion]) -> list[LinkedParam]:
    return [
        LinkedParam(
            link.param,
            to_wire(k.resolved_params[link.param].value),
            k.display_name_of(link.param),
        )
        for k in criteria
        for link in k.answers
        if link.requirement == c.id
        and link.param is not None
        and link.param in k.resolved_params
    ]


def linked_analyses(
    c: Constraint, criteria: Sequence[Criterion]
) -> list[AnalysisBinding]:
    return [k.analysis for k in linking(c, criteria) if k.analysis is not None]


def not_verified(c: Constraint, why: str) -> GroundedConstraint:
    return GroundedConstraint(constraint=c, status=ConstraintStatus.GROUNDED, note=why)


def unread(
    c: Constraint, realized: RealizedSpec, why: str, *, cut: AnalysisCut | None = None
) -> GroundedConstraint:
    linked = linking(c, realized.criteria)
    uncut = cut is not None and any(
        k.analysis is not None
        and k.analysis.method is not None
        and cut(k.analysis) is None
        for k in linked
    )
    if uncut or any(k.pending_analysis for k in linked):
        return awaiting_analysis(c)
    return not_verified(c, why)


def linked_by_none(c: Constraint, criteria: Sequence[Criterion]) -> bool:
    return c.kind in COMPARED_THROUGH_A_LINK and not linking(c, criteria)
