"""What a constraint claims, when it blocks, and how two statements merge."""

from __future__ import annotations

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    is_blocking,
    merge_constraints,
    provisional_constraints,
)


def _data_type(
    value: str,
    source: ConstraintSource = ConstraintSource.ASSUMED,
    *,
    hard: bool = True,
) -> Constraint:
    return Constraint(
        kind=ConstraintKind.DATA_TYPE,
        requested_value=value,
        source=source,
        label="data type",
        hard=hard,
    )


def _combination(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value=value,
        label="how the evidence combines",
        source=ConstraintSource.USER_EXPLICIT,
    )


def test_constraint_defaults_to_assumed() -> None:
    constraint = Constraint(
        kind=ConstraintKind.DATA_TYPE, requested_value="RNA-Seq", label="data type"
    )

    assert constraint.source is ConstraintSource.ASSUMED


def test_blocking_only_for_user_explicit_unmet() -> None:
    explicit = _data_type("RNA-Seq", ConstraintSource.USER_EXPLICIT)
    assumed = explicit.model_copy(update={"source": ConstraintSource.ASSUMED})

    verdicts = [
        is_blocking(
            GroundedConstraint(
                constraint=explicit, status=ConstraintStatus.UNGROUNDABLE, note="x"
            )
        ),
        is_blocking(
            GroundedConstraint(
                constraint=explicit,
                status=ConstraintStatus.SUBSTITUTED,
                realized_value="microarray",
                note="x",
            )
        ),
        is_blocking(
            GroundedConstraint(
                constraint=explicit,
                status=ConstraintStatus.GROUNDED,
                realized_value="RNA-Seq",
            )
        ),
        is_blocking(
            GroundedConstraint(
                constraint=assumed, status=ConstraintStatus.UNGROUNDABLE, note="x"
            )
        ),
    ]

    assert verdicts == [True, True, False, False]


def test_soft_user_explicit_constraint_does_not_block() -> None:
    soft = _data_type(
        "RNA-Seq preferred, microarray fallback ok",
        ConstraintSource.USER_EXPLICIT,
        hard=False,
    )
    substituted = GroundedConstraint(
        constraint=soft,
        status=ConstraintStatus.SUBSTITUTED,
        realized_value="microarray",
    )

    assert is_blocking(substituted) is False


def test_provisional_constraints_are_pending_and_non_blocking() -> None:
    [grounded] = provisional_constraints(
        [_data_type("RNA-Seq", ConstraintSource.USER_EXPLICIT)]
    )

    assert grounded.status is ConstraintStatus.PROVISIONAL
    assert grounded.realized_value is None
    assert is_blocking(grounded) is False


class TestMergingRequirements:
    def test_merge_explicit_overrides_assumed_per_kind_and_keeps_its_source(
        self,
    ) -> None:
        """Who stated a value is decided when the thread records it."""
        provisional = [
            _data_type("RNA-Seq or microarray"),
            Constraint(
                kind=ConstraintKind.ORGANISM,
                requested_value="Aedes aegypti",
                label="organism",
                source=ConstraintSource.ASSUMED,
            ),
        ]

        stated = _data_type("RNA-Seq only").model_copy(
            update={"source": ConstraintSource.USER_EXPLICIT},
        )

        merged = merge_constraints(provisional, [stated])

        by_kind = {c.kind: c for c in merged}
        assert by_kind[ConstraintKind.DATA_TYPE].requested_value == "RNA-Seq only"
        assert (
            by_kind[ConstraintKind.DATA_TYPE].source is ConstraintSource.USER_EXPLICIT
        )
        assert by_kind[ConstraintKind.ORGANISM].source is ConstraintSource.ASSUMED

    def test_two_combination_requirements_both_survive_the_merge(self) -> None:
        """A combination names its own criteria, so a second one is a new
        dimension."""
        merged = merge_constraints(
            [],
            [
                _combination("mass spec OR DeRisi expression"),
                _combination("kinase domain AND phosphatase domain"),
            ],
        )

        assert [c.requested_value for c in merged] == [
            "mass spec OR DeRisi expression",
            "kinase domain AND phosphatase domain",
        ]

    def test_the_same_combination_stated_twice_is_one_requirement(self) -> None:
        merged = merge_constraints(
            [_combination("mass spec OR DeRisi expression")],
            [_combination("mass spec OR DeRisi expression")],
        )

        assert len(merged) == 1
        assert merged[0].requested_value == "mass spec OR DeRisi expression"

    def test_another_kind_still_collapses_per_dimension(self) -> None:
        merged = merge_constraints(
            [_data_type("microarray")], [_data_type("RNA-Seq only")]
        )

        assert [c.requested_value for c in merged] == ["RNA-Seq only"]


def _other(value: str, source: ConstraintSource) -> Constraint:
    return Constraint(
        kind=ConstraintKind.OTHER, requested_value=value, source=source, label="other"
    )


def test_two_distinct_other_values_both_survive_the_merge() -> None:
    merged = merge_constraints(
        [_other("signal peptide", ConstraintSource.ASSUMED)],
        [_other("zinc finger domain", ConstraintSource.USER_EXPLICIT)],
    )

    assert [c.requested_value for c in merged] == [
        "signal peptide",
        "zinc finger domain",
    ]


def test_a_reworded_other_value_collapses_to_the_stated_one() -> None:
    """Values whose non-filler words are equal are one requirement."""
    merged = merge_constraints(
        [_other("transmembrane domain", ConstraintSource.ASSUMED)],
        [_other("a transmembrane domain", ConstraintSource.USER_EXPLICIT)],
    )

    assert [(c.requested_value, c.source) for c in merged] == [
        ("a transmembrane domain", ConstraintSource.USER_EXPLICIT)
    ]
