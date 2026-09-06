"""Grounding a stated constraint against the strategy that realizes it."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence

from pydantic import Field
from veupathdb.domain.strategy.combination_check import (
    combination_violation,
    match_terms,
    meeting_operator,
)
from veupathdb.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    PercentileRequest,
)
from veupathdb.domain.strategy.operational_spec import Criterion, SpecStructure
from veupathdb.model import CamelModel

_SIGNIFICANCE_RE = re.compile(
    r"p_?value|p_?adj|fdr|q_?value|significance", re.IGNORECASE
)
_MICROARRAY_RE = re.compile(r"microarray", re.IGNORECASE)
_RNASEQ_REQUEST_RE = re.compile(r"rna[\s_-]?seq", re.IGNORECASE)
_EXPRESSION_SEARCH_RE = re.compile(r"rnaseq|microarray", re.IGNORECASE)


class _RealizedSpec(CamelModel):
    """The bound facts a constraint is grounded against: the criteria's WDK
    search names, the union of their parameter names, the values bound to them,
    and the tree the criteria are combined in."""

    search_names: list[str] = Field(default_factory=list)
    param_names: frozenset[str] = Field(default_factory=frozenset)
    param_values: dict[str, str] = Field(default_factory=dict)
    structure: SpecStructure | None = None
    criteria: list[Criterion] = Field(default_factory=list)


def _ground_data_type(c: Constraint, realized: _RealizedSpec) -> GroundedConstraint:
    expr = [s for s in realized.search_names if _EXPRESSION_SEARCH_RE.search(s)]
    if not expr:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            note="no expression search in the strategy",
        )
    wants_rnaseq = bool(_RNASEQ_REQUEST_RE.search(c.requested_value))
    all_microarray = all(_MICROARRAY_RE.search(s) for s in expr)
    if wants_rnaseq and all_microarray:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.SUBSTITUTED,
            realized_value="microarray",
            note="requested RNA-Seq but only microarray searches were selected",
        )
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        realized_value="rna-seq" if wants_rnaseq else "microarray",
    )


def _ground_threshold(c: Constraint, realized: _RealizedSpec) -> GroundedConstraint:
    if any(_SIGNIFICANCE_RE.search(name) for name in realized.param_names):
        return GroundedConstraint(constraint=c, status=ConstraintStatus.GROUNDED)
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.UNGROUNDABLE,
        note="no selected search exposes a significance parameter",
    )


def _ground_fold_change(c: Constraint, realized: _RealizedSpec) -> GroundedConstraint:
    if any("fold_change" in name for name in realized.param_names):
        return GroundedConstraint(constraint=c, status=ConstraintStatus.GROUNDED)
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.UNGROUNDABLE,
        note="no fold_change parameter in the strategy",
    )


_PERCENTILE_PARAM_RE = re.compile(r"percentile", re.IGNORECASE)
# A "top" share is a lower bound on the percentile; a "bottom" share is an
# upper bound. The name of the WDK parameter says which end it holds.
_BOUND_WORD: dict[str, str] = {"top": "min", "bottom": "max"}


def _plain(number: float) -> str:
    return str(int(number)) if number.is_integer() else str(number)


def _percentile_bound(
    request: PercentileRequest, realized: _RealizedSpec
) -> tuple[str, str] | None:
    named = {
        name: value
        for name, value in realized.param_values.items()
        if _PERCENTILE_PARAM_RE.search(name)
    }
    if not named:
        return None
    word = _BOUND_WORD[request.direction]
    at_end = {name: value for name, value in named.items() if word in name.lower()}
    chosen = at_end or named
    if len(chosen) != 1:
        return None
    return next(iter(chosen.items()))


def _ground_percentile(c: Constraint, realized: _RealizedSpec) -> GroundedConstraint:
    request = PercentileRequest.parse(f"{c.requested_value} {c.label}")
    if request is None:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            note="the requested share and direction could not be read",
        )
    found = _percentile_bound(request, realized)
    if found is None:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            note="no percentile parameter in the strategy",
        )
    name, raw = found
    try:
        bound = float(raw)
    except ValueError:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            realized_value=raw,
            note=f"{name} holds {raw!r}, which is not a percentile",
        )
    if bound == request.bound:
        return GroundedConstraint(
            constraint=c, status=ConstraintStatus.GROUNDED, realized_value=raw
        )
    meant = _plain(request.share_of(bound))
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.SUBSTITUTED,
        realized_value=raw,
        note=f"bound {_plain(bound)} means {request.direction} {meant}%",
    )


def _abstained(c: Constraint, why: str) -> GroundedConstraint:
    """A combination this strategy gives no answer about.

    An abstention never blocks: the words the user chose name no criterion of
    the spec, so nothing here contradicts them.
    """
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        note=f"the combination check abstained: {why}",
    )


def _ground_combination(c: Constraint, realized: _RealizedSpec) -> GroundedConstraint:
    request = CombinationRequest.parse(c.requested_value)
    if request is None:
        return _abstained(c, "the requirement states no single operator")
    matched = match_terms(request.terms, realized.criteria)
    if matched is None:
        return _abstained(c, "its terms name no distinct criteria of this strategy")
    if realized.structure is None:
        return _abstained(c, "the strategy has no structure yet")
    violation = combination_violation(request, matched.values(), realized.structure)
    if violation is not None:
        return GroundedConstraint(
            constraint=c, status=ConstraintStatus.UNGROUNDABLE, note=violation
        )
    found = meeting_operator(realized.structure, matched.values())
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        realized_value=None if found is None else found.value,
    )


_HANDLERS = {
    ConstraintKind.DATA_TYPE: _ground_data_type,
    ConstraintKind.STATISTICAL_THRESHOLD: _ground_threshold,
    ConstraintKind.FOLD_CHANGE: _ground_fold_change,
    ConstraintKind.PERCENTILE: _ground_percentile,
    ConstraintKind.COMBINATION: _ground_combination,
}


def ground_constraints(
    constraints: list[Constraint],
    *,
    search_names: Collection[str],
    param_names: Collection[str],
    param_values: Mapping[str, str],
    structure: SpecStructure | None = None,
    criteria: Sequence[Criterion] = (),
) -> list[GroundedConstraint]:
    """Ground each constraint against the realized strategy facts (the criteria's
    bound WDK search names, the union of their parameter names, the values
    bound to them, and the tree they are combined in)."""
    realized = _RealizedSpec(
        search_names=list(search_names),
        param_names=frozenset(param_names),
        param_values=dict(param_values),
        structure=structure,
        criteria=list(criteria),
    )
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
