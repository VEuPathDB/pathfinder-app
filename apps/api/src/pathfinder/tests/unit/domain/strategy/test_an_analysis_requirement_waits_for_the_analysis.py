"""A threshold, fold or data-type requirement is provisional while the analysis
that states it has not run, and is grounded against the cuts the analysis holds."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    is_blocking,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests.unit.domain.strategy._analysis import analysed, binding, pending


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=kind.value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_P = _stated(ConstraintKind.STATISTICAL_THRESHOLD, "p 0.001")
_NO_FOLD = _stated(ConstraintKind.FOLD_CHANGE, "no fold change cutoff")
_TWO_FOLD = _stated(ConstraintKind.FOLD_CHANGE, "2-fold")
_RNA_SEQ = _stated(ConstraintKind.DATA_TYPE, "RNA-Seq")

_ORTHOLOGS = Criterion(
    id="c_orthologs",
    text="with orthologs in Aspergillus",
    search_name="GenesOrthologousToAGivenOrganism",
    resolved_params={
        "organism": BoundValue(value=StringValue(value="Aspergillus"), source="stated")
    },
)


def _spec(*criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(goal="DESeq genes at p 0.001", criteria=list(criteria))


def _statuses(spec: OperationalSpec, *stated: Constraint) -> list[ConstraintStatus]:
    return [g.status for g in ground_against_spec(list(stated), spec)]


def test_each_analysis_requirement_is_provisional_while_the_analysis_waits() -> None:
    grounded = ground_against_spec(
        [_P, _NO_FOLD, _TWO_FOLD, _RNA_SEQ], _spec(pending(), _ORTHOLOGS)
    )

    assert [g.status for g in grounded] == [ConstraintStatus.PROVISIONAL] * 4
    assert not any(is_blocking(g) for g in grounded)


def test_an_analysis_holding_the_cuts_grounds_both_requirements() -> None:
    held = binding(significance=0.001).model_copy(
        update={"effect_size_threshold": None}
    )

    assert _statuses(_spec(analysed(bound=held)), _P, _NO_FOLD) == [
        ConstraintStatus.GROUNDED,
        ConstraintStatus.GROUNDED,
    ]


def test_an_analysis_cut_at_log2_zero_grounds_no_fold_cutoff() -> None:
    held = binding().model_copy(update={"effect_size_threshold": 0.0})

    [fold] = ground_against_spec([_NO_FOLD], _spec(analysed(bound=held)))

    assert (fold.status, fold.realized_value) == (ConstraintStatus.GROUNDED, "0")


def test_an_analysis_with_a_fold_cut_substitutes_no_fold_cutoff() -> None:
    [fold] = ground_against_spec([_NO_FOLD], _spec(analysed()))

    assert (fold.status, fold.note) == (
        ConstraintStatus.SUBSTITUTED,
        "built 2-fold (log2 1) where no fold change cutoff was asked",
    )


def test_a_compute_with_no_significance_read_is_provisional() -> None:
    held = binding().model_copy(update={"significance_threshold": None})

    assert _statuses(_spec(analysed(bound=held), _ORTHOLOGS), _P) == [
        ConstraintStatus.PROVISIONAL
    ]


def test_a_bound_search_and_no_analysis_leaves_the_threshold_ungroundable() -> None:
    assert _statuses(_spec(_ORTHOLOGS), _P, _NO_FOLD) == [
        ConstraintStatus.UNGROUNDABLE,
        ConstraintStatus.UNGROUNDABLE,
    ]
