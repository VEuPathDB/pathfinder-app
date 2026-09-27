"""A diff removes built steps and does nothing else, or it does more."""

from __future__ import annotations

from pathfinder.domain.strategy.spec_diff import (
    CriterionChange,
    SpecDiff,
    steps_only_removed,
)

_BUILT = frozenset({"step_signal", "step_tm"})


def _diff(*changes: CriterionChange) -> SpecDiff:
    return SpecDiff(changes=list(changes), structure_changed=True)


def test_a_removal_only_diff_names_the_built_step_it_drops() -> None:
    diff = _diff(
        CriterionChange(criterion_id="step_signal", disposition="kept"),
        CriterionChange(criterion_id="step_tm", disposition="dropped"),
    )

    assert steps_only_removed(diff, _BUILT) == ["step_tm"]


def test_a_removal_with_a_change_is_not_removal_only() -> None:
    diff = _diff(
        CriterionChange(
            criterion_id="step_signal",
            disposition="changed",
            changed_params={"min_tm": "2"},
        ),
        CriterionChange(criterion_id="step_tm", disposition="dropped"),
    )

    assert steps_only_removed(diff, _BUILT) == []


def test_a_drop_of_a_criterion_never_built_names_no_step() -> None:
    diff = _diff(
        CriterionChange(criterion_id="step_signal", disposition="kept"),
        CriterionChange(criterion_id="framed_only", disposition="dropped"),
    )

    assert steps_only_removed(diff, _BUILT) == []


def test_a_drop_with_an_addition_is_a_replacement() -> None:
    diff = _diff(
        CriterionChange(criterion_id="step_signal", disposition="kept"),
        CriterionChange(criterion_id="step_tm", disposition="dropped"),
        CriterionChange(
            criterion_id="exported_genes",
            disposition="added",
            changed_params={"ds": "x"},
        ),
    )

    assert steps_only_removed(diff, _BUILT) == []
