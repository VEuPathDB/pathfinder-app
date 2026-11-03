"""A fold-change requirement against the threshold its link names, compared on
the scale the threshold declares."""

from __future__ import annotations

from pathfinder.domain.requirement_checks import grounded_check
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    FoldChangeValue,
    FoldDirection,
    GroundedConstraint,
    is_blocking,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from pathfinder.tests.unit.domain.strategy._linked_values import linked, requirement

_MICROARRAY_SEARCH = (
    "GenesByMicroarrayaaegLVP_AGWG_microarrayExpression_GSE22339_male_vs_female_RSRC"
)


def _fold(
    cut: float | None, *, scale: str = "fold", direction: FoldDirection = "either"
) -> Constraint:
    return requirement(
        ConstraintKind.FOLD_CHANGE,
        FoldChangeValue.model_validate(
            {"cut": cut, "scale": scale, "direction": direction}
        ),
    )


def _fungidb_export(
    held: Constraint, effect_size_threshold: float | None, direction: str = "upOnly"
) -> Criterion:
    """The fungidb DESeq step, serum 37C over 30C YEPD."""
    return Criterion(
        id="step_a036deb7",
        text="upregulated in hyphae compared with yeast form",
        answers=[RequirementLink(requirement=held.id)],
        analysis=AnalysisBinding.model_validate(
            {
                "datasetId": "DS_fungidb_hyphae",
                "method": "DESeq",
                "effectDirection": direction,
                "effectSizeThreshold": effect_size_threshold,
                "effectSizeLabel": "log2(Fold Change)",
                "significanceThreshold": 0.05,
                "words": "serum 37C over 30C YEPD",
            }
        ),
    )


def _against(held: Constraint, criterion: Criterion) -> GroundedConstraint:
    [grounded] = ground_against_spec(
        [held], OperationalSpec(goal="g", criteria=[criterion])
    )
    return grounded


class TestAFoldChangeIsComparedInTheParametersUnit:
    def test_a_log2_cut_at_the_folds_number_is_not_the_fold_asked(self) -> None:
        held = _fold(1.5)

        grounded = _against(held, _fungidb_export(held, 1.5))

        assert (
            grounded.status,
            grounded.realized_param,
            grounded.realized_value,
            grounded.note,
        ) == (
            ConstraintStatus.SUBSTITUTED,
            "effect_size_threshold",
            "1.5",
            "built 2.82843-fold (log2 1.5) where 1.5-fold was asked",
        )
        assert is_blocking(grounded)

    def test_a_log2_cut_at_the_folds_log2_meets_it(self) -> None:
        held = _fold(1.5)

        grounded = _against(held, _fungidb_export(held, 0.585))

        assert (grounded.status, grounded.realized_value) == (
            ConstraintStatus.GROUNDED,
            "0.585",
        )

    def test_a_log2_cut_asked_on_log2_meets_the_same_number(self) -> None:
        held = _fold(5, scale="log2")

        grounded = _against(held, _fungidb_export(held, 5))

        assert grounded.status is ConstraintStatus.GROUNDED

    def test_a_fold_parameter_at_another_fold_is_not_the_fold_asked(self) -> None:
        held = _fold(3)
        microarray = linked(
            held,
            {"fold_change": "2"},
            "fold_change",
            search=_MICROARRAY_SEARCH,
            shown={"fold_change": "Fold change >="},
        )

        grounded = _against(held, microarray)

        assert (grounded.status, grounded.note) == (
            ConstraintStatus.SUBSTITUTED,
            "built 2-fold where 3-fold was asked",
        )

    def test_a_log2_parameter_at_the_folds_log2_meets_it(self) -> None:
        held = _fold(2)
        rnaseq = linked(
            held,
            {"fold_change": "1"},
            "fold_change",
            search="GenesByRNASeqFoldChange",
            shown={"fold_change": "log2 fold change >="},
        )

        assert _against(held, rnaseq).status is ConstraintStatus.GROUNDED


class TestTheDirectionIsTheAnalysisDirection:
    def test_a_direction_the_analysis_cuts_meets_it(self) -> None:
        held = _fold(None, direction="up")

        grounded = _against(held, _fungidb_export(held, 1.0))

        assert (grounded.status, grounded.realized_param, grounded.realized_value) == (
            ConstraintStatus.GROUNDED,
            "effect_direction",
            "upOnly",
        )

    def test_another_direction_fails_its_check(self) -> None:
        held = _fold(2, direction="up")

        grounded = _against(held, _fungidb_export(held, 1.0, "upAndDown"))

        assert (grounded.status, grounded.note, grounded_check(grounded).status) == (
            ConstraintStatus.SUBSTITUTED,
            "built upAndDown where up was asked",
            "fail",
        )


class TestNoFoldCut:
    def test_an_uncut_analysis_meets_no_fold_cutoff(self) -> None:
        held = _fold(1)

        assert _against(held, _fungidb_export(held, None)).status is (
            ConstraintStatus.GROUNDED
        )

    def test_an_analysis_at_log2_zero_meets_no_fold_cutoff(self) -> None:
        held = _fold(1)

        grounded = _against(held, _fungidb_export(held, 0.0))

        assert (grounded.status, grounded.realized_value) == (
            ConstraintStatus.GROUNDED,
            "0",
        )

    def test_an_analysis_with_a_fold_cut_substitutes_no_fold_cutoff(self) -> None:
        held = _fold(1)

        grounded = _against(held, _fungidb_export(held, 1.0))

        assert (grounded.status, grounded.note) == (
            ConstraintStatus.SUBSTITUTED,
            "built 2-fold (log2 1) where 1-fold was asked",
        )


def test_a_fold_parameter_no_link_names_is_not_verified() -> None:
    held = _fold(2)
    unlinked = linked(held, {"fold_change": "2"}, search=_MICROARRAY_SEARCH)

    grounded = _against(held, unlinked)

    assert (grounded.status, grounded_check(grounded).status) == (
        ConstraintStatus.GROUNDED,
        "unchecked",
    )
    assert not is_blocking(grounded)
