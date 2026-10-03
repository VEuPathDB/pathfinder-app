"""A requirement is provisional while the spec binds no search and holds no
analysis, and is grounded against the spec once it binds one."""

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

_GOAL = "Find P. falciparum 3D7 genes up 2-fold in RNA-Seq, p below 0.05"


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=kind.value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_REQUIREMENTS = [
    _stated(ConstraintKind.ORGANISM, "P. falciparum 3D7"),
    _stated(ConstraintKind.FOLD_CHANGE, "2-fold"),
    _stated(ConstraintKind.DATA_TYPE, "RNA-Seq"),
    _stated(ConstraintKind.STATISTICAL_THRESHOLD, "p below 0.05"),
    _stated(ConstraintKind.PERCENTILE, "top 10 percent"),
]


def test_every_requirement_is_provisional_while_no_search_is_bound() -> None:
    grounded = ground_against_spec(_REQUIREMENTS, OperationalSpec(goal=_GOAL))

    assert [(g.constraint.key, g.status) for g in grounded] == [
        (c.key, ConstraintStatus.PROVISIONAL) for c in _REQUIREMENTS
    ]
    assert {g.note for g in grounded} == {"no search is bound yet"}
    assert not any(is_blocking(g) for g in grounded)


def test_a_criterion_with_no_search_binds_nothing() -> None:
    spec = OperationalSpec(
        goal=_GOAL,
        criteria=[Criterion(id="c_gpi", text="with a predicted GPI anchor")],
    )

    grounded = ground_against_spec(_REQUIREMENTS, spec)

    assert {g.status for g in grounded} == {ConstraintStatus.PROVISIONAL}


def test_a_bound_search_with_no_fold_parameter_leaves_the_fold_ungroundable() -> None:
    spec = OperationalSpec(
        goal=_GOAL,
        criteria=[
            Criterion(
                id="c_signal",
                text="with a signal peptide",
                search_name="GenesWithSignalPeptide",
                resolved_params={
                    "organism": BoundValue(
                        value=StringValue(value="Plasmodium falciparum 3D7"),
                        source="stated",
                    )
                },
            )
        ],
    )

    [fold] = ground_against_spec([_stated(ConstraintKind.FOLD_CHANGE, "2-fold")], spec)

    assert fold.status is ConstraintStatus.UNGROUNDABLE
    assert is_blocking(fold)
