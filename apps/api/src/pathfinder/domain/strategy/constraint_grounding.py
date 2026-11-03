"""Grounding a stated constraint against the strategy that realizes it."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pathfinder.domain.log2_scale import scale_of
from pathfinder.domain.strategy.combination_check import (
    exclusion_stands_over,
    meeting_operator,
    transform_stands_over,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    DataKind,
    DataTypeValue,
    GroundedConstraint,
)
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.fold_grounding import FOLD_PARAM, ground_fold_change
from pathfinder.domain.strategy.linked_values import linking, not_verified
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.organism_scope import selected_organisms
from pathfinder.domain.strategy.realized_spec import RealizedSpec, awaiting_analysis
from pathfinder.domain.strategy.value_grounding import (
    UNTYPED,
    ground_percentile,
    ground_significance,
)

_SIGNIFICANCE_RE = re.compile(
    r"p_?value|p_?adj|fdr|q_?value|significance", re.IGNORECASE
)
_ASSAYS: tuple[tuple[re.Pattern[str], DataKind], ...] = (
    (re.compile(r"rna[\s_-]?seq", re.IGNORECASE), "rna_seq"),
    (re.compile(r"microarray", re.IGNORECASE), "microarray"),
)
_MIN_MEMBERS = 2


def _assay(mark: str | None) -> DataKind | None:
    if mark is None:
        return None
    return next((data for found, data in _ASSAYS if found.search(mark)), None)


def _ground_data_type(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    match c.value:
        case DataTypeValue() as asked:
            pass
        case _:
            return not_verified(c, UNTYPED)
    linked = linking(c, realized.criteria)
    if not linked:
        return not_verified(c, "no criterion links it")
    ran = {data for k in linked if (data := _assay(realized.marks.run_on(k)))}
    if asked.data in ran:
        return GroundedConstraint(
            constraint=c, status=ConstraintStatus.GROUNDED, realized_value=asked.data
        )
    if ran:
        [built] = ran
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.SUBSTITUTED,
            realized_value=built,
            note=f"asked {asked.data}, the steps that link it run on {built}",
        )
    if any(k.pending_analysis for k in linked):
        return awaiting_analysis(c)
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.UNGROUNDABLE,
        note="no step that links it runs on expression data",
    )


_PERCENTILE_PARAM_RE = re.compile(r"percentile", re.IGNORECASE)


def dimension_of_parameter(name: str, display_name: str) -> ConstraintKind:
    """The dimension a value of this parameter states, read from its names."""
    if _PERCENTILE_PARAM_RE.search(name) or _PERCENTILE_PARAM_RE.search(display_name):
        return ConstraintKind.PERCENTILE
    if _SIGNIFICANCE_RE.search(name):
        return ConstraintKind.STATISTICAL_THRESHOLD
    if FOLD_PARAM in name or scale_of(display_name) is not None:
        return ConstraintKind.FOLD_CHANGE
    return ConstraintKind.OTHER


def _abstained(c: Constraint, why: str) -> GroundedConstraint:
    """A combination this strategy gives no answer about.

    An abstention never blocks: no criterion this check can read answers the
    combination, so nothing here contradicts it.
    """
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        note=f"the combination check abstained: {why}",
    )


def _ids(criteria: Sequence[Criterion], *roles: str) -> list[str]:
    return [c.id for c in criteria if c.role in roles]


def _why_it_says_nothing(
    linked: Sequence[Criterion], structure: SpecStructure
) -> str | None:
    """Why this tree answers nothing about the held combination, or None.

    A combine is read over two members or none. A transform the tree holds
    away from those members, and an exclusion it subtracts from no branch,
    describe another tree than this one.
    """
    members = _ids(linked, "filter", "seed")
    if len(members) < _MIN_MEMBERS:
        return "fewer than two criteria a combine joins link it"
    if any(
        not transform_stands_over(structure, transform_id, members)
        for transform_id in _ids(linked, "transform")
    ):
        return "a transform that links it stands over none of those criteria"
    if any(
        not exclusion_stands_over(structure, exclude_id, members)
        for exclude_id in _ids(linked, "exclude")
    ):
        return "a criterion it removes is subtracted from no branch"
    return None


def _ground_combination(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    linked = [crit for crit in realized.criteria if crit.links(c.id)]
    if not linked:
        return _abstained(c, "no criterion links it")
    if realized.structure is None:
        return _abstained(c, "the strategy has no structure yet")
    silent = _why_it_says_nothing(linked, realized.structure)
    if silent is not None:
        return _abstained(c, silent)
    found = meeting_operator(realized.structure, _ids(linked, "filter", "seed"))
    if found is None:
        return _abstained(c, "the criteria that link it meet at no combine")
    return _abstained(
        c,
        f"the criteria that link it meet at {found.value}, and that combine is "
        f"read against the researcher's words",
    )


def _realized_organism(c: Constraint, criterion: Criterion) -> tuple[str, str] | None:
    param, organism = criterion.organism_param, c.organism
    if param and organism is not None and organism in selected_organisms(criterion):
        return (param, organism)
    if not criterion.links(c.id):
        return None
    return next(
        (
            (name, held.taxon.name)
            for name, held in criterion.resolved_params.items()
            if held.taxon is not None
        ),
        None,
    )


def _ground_organism(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    for criterion in realized.criteria:
        found = _realized_organism(c, criterion)
        if found is not None:
            return GroundedConstraint(
                constraint=c,
                status=ConstraintStatus.GROUNDED,
                realized_param=found[0],
                realized_value=found[1],
            )
    return GroundedConstraint(constraint=c, status=ConstraintStatus.GROUNDED)


_NO_MARKS = DataMarks()

_HANDLERS = {
    ConstraintKind.DATA_TYPE: _ground_data_type,
    ConstraintKind.STATISTICAL_THRESHOLD: ground_significance,
    ConstraintKind.FOLD_CHANGE: ground_fold_change,
    ConstraintKind.PERCENTILE: ground_percentile,
    ConstraintKind.COMBINATION: _ground_combination,
    ConstraintKind.ORGANISM: _ground_organism,
}


def ground_constraints(
    constraints: list[Constraint], realized: RealizedSpec
) -> list[GroundedConstraint]:
    """Ground each constraint against the realized strategy facts.

    While the strategy realizes nothing, every constraint is provisional: no
    search is bound that could state it or fail to.
    """
    if realized.realizes_nothing:
        return [
            GroundedConstraint(
                constraint=c,
                status=ConstraintStatus.PROVISIONAL,
                note="no search is bound yet",
            )
            for c in constraints
        ]
    out: list[GroundedConstraint] = []
    for c in constraints:
        handler = _HANDLERS.get(c.kind)
        if handler is None:
            out.append(
                GroundedConstraint(constraint=c, status=ConstraintStatus.GROUNDED)
            )
        else:
            out.append(handler(c, realized))
    return out


def ground_against_spec(
    constraints: Sequence[Constraint],
    spec: OperationalSpec,
    *,
    marks: DataMarks = _NO_MARKS,
) -> list[GroundedConstraint]:
    """Ground each constraint against the facts this spec realizes and what the
    site says each criterion runs on."""
    return ground_constraints(
        list(constraints),
        RealizedSpec(
            search_names=[c.search_name for c in spec.criteria if c.search_name],
            structure=spec.structure,
            criteria=spec.criteria,
            marks=marks,
        ),
    )
