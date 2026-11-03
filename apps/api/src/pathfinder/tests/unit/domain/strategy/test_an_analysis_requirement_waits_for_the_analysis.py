"""A threshold or fold requirement is provisional while the analysis that links
it has not run, and is grounded against the cuts the analysis holds."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    FoldChangeValue,
    RequirementValue,
    SignificanceValue,
    is_blocking,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from pathfinder.tests.unit.domain.strategy._analysis import analysed, binding, pending


def _stated(kind: ConstraintKind, words: str, value: RequirementValue) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=words,
        label=kind.value,
        source=ConstraintSource.USER_EXPLICIT,
        value=value,
    )


_P = _stated(
    ConstraintKind.STATISTICAL_THRESHOLD, "p 0.001", SignificanceValue(at_most=0.001)
)
_NO_FOLD = _stated(
    ConstraintKind.FOLD_CHANGE, "no fold change cutoff", FoldChangeValue(cut=1)
)
_TWO_FOLD = _stated(ConstraintKind.FOLD_CHANGE, "2-fold", FoldChangeValue(cut=2))
_RNA_SEQ = Constraint(
    kind=ConstraintKind.DATA_TYPE,
    requested_value="RNA-Seq",
    label="data type",
    source=ConstraintSource.USER_EXPLICIT,
)

_ORTHOLOGS = Criterion(
    id="c_orthologs",
    text="with orthologs in Aspergillus",
    search_name="GenesOrthologousToAGivenOrganism",
    resolved_params={
        "organism": BoundValue(value=StringValue(value="Aspergillus"), source="stated")
    },
)


def _linking(criterion: Criterion, *held: Constraint) -> Criterion:
    return criterion.model_copy(
        update={"answers": [RequirementLink(requirement=c.id) for c in held]}
    )


def _spec(*criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(goal="DESeq genes at p 0.001", criteria=list(criteria))


def _statuses(spec: OperationalSpec, *stated: Constraint) -> list[ConstraintStatus]:
    return [g.status for g in ground_against_spec(list(stated), spec)]


def test_each_analysis_requirement_is_provisional_while_the_analysis_waits() -> None:
    waiting = _linking(pending(), _P, _NO_FOLD, _TWO_FOLD)

    grounded = ground_against_spec(
        [_P, _NO_FOLD, _TWO_FOLD, _RNA_SEQ], _spec(waiting, _ORTHOLOGS)
    )

    assert [g.status for g in grounded] == [ConstraintStatus.PROVISIONAL] * 4
    assert not any(is_blocking(g) for g in grounded)


def test_an_analysis_holding_the_cuts_grounds_both_requirements() -> None:
    held = binding(significance=0.001).model_copy(
        update={"effect_size_threshold": None}
    )

    assert _statuses(
        _spec(_linking(analysed(bound=held), _P, _NO_FOLD)), _P, _NO_FOLD
    ) == [
        ConstraintStatus.GROUNDED,
        ConstraintStatus.GROUNDED,
    ]


def test_a_compute_with_no_significance_read_is_provisional() -> None:
    held = binding().model_copy(update={"significance_threshold": None})

    assert _statuses(_spec(_linking(analysed(bound=held), _P), _ORTHOLOGS), _P) == [
        ConstraintStatus.PROVISIONAL
    ]


def test_a_bound_search_and_no_link_leaves_the_threshold_not_verified() -> None:
    grounded = ground_against_spec([_P, _NO_FOLD], _spec(_ORTHOLOGS))

    assert [(g.status, g.note) for g in grounded] == [
        (ConstraintStatus.GROUNDED, "no criterion links it to a parameter")
    ] * 2
    assert not any(is_blocking(g) for g in grounded)
