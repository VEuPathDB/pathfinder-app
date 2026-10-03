"""A fold-change requirement against a threshold, compared on the scale the
threshold declares."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue, to_wire

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraint_grounding import ground_constraints
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    is_blocking,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
)
from pathfinder.domain.strategy.realized_spec import RealizedSpec
from pathfinder.tests._support.bound_values import bound

# The realized facts of a single microarray fold-change leaf.
_MICROARRAY_SEARCH = (
    "GenesByMicroarrayaaegLVP_AGWG_microarrayExpression_GSE22339_male_vs_female_RSRC"
)


def _explicit(kind: ConstraintKind, value: str, label: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
        label=label,
    )


def _fungidb_export(effect_size_threshold: float) -> Criterion:
    """The fungidb DESeq step, serum 37C over 30C YEPD, up only."""
    return Criterion(
        id="step_a036deb7",
        text="upregulated in hyphae compared with yeast form",
        analysis=AnalysisBinding(
            dataset_id="DS_fungidb_hyphae",
            method="DESeq",
            effect_direction="upOnly",
            effect_size_threshold=effect_size_threshold,
            effect_size_label="log2(Fold Change)",
            significance_threshold=0.05,
            words="serum 37C over 30C YEPD",
        ),
    )


def _fold(criteria: list[Criterion], requested: str = "1.5-fold") -> GroundedConstraint:
    values = {name: value for c in criteria for name, value in c.param_values.items()}
    [grounded] = ground_constraints(
        [_explicit(ConstraintKind.FOLD_CHANGE, requested, "fold change")],
        RealizedSpec(
            search_names=[c.search_name for c in criteria if c.search_name],
            param_names=frozenset(values),
            param_values={name: to_wire(value) for name, value in values.items()},
            criteria=criteria,
        ),
    )
    return grounded


class TestAFoldChangeIsComparedInTheParametersUnit:
    def test_a_log2_cut_at_the_folds_number_is_not_the_fold_asked(self) -> None:
        grounded = _fold([_fungidb_export(1.5)])

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
        grounded = _fold([_fungidb_export(0.585)])

        assert (grounded.status, grounded.realized_value) == (
            ConstraintStatus.GROUNDED,
            "0.585",
        )

    def test_a_fold_parameter_at_another_fold_is_not_the_fold_asked(self) -> None:
        microarray = Criterion(
            id="c_microarray",
            text="male over female",
            search_name=_MICROARRAY_SEARCH,
            resolved_params=bound({"fold_change": StringValue(value="2")}),
            param_display_names={"fold_change": "Fold change >="},
        )

        grounded = _fold([microarray], requested="3-fold")

        assert (grounded.status, grounded.note) == (
            ConstraintStatus.SUBSTITUTED,
            "built 2-fold where 3-fold was asked",
        )

    def test_a_log2_parameter_at_the_folds_log2_meets_it(self) -> None:
        rnaseq = Criterion(
            id="c_rnaseq",
            text="twofold up",
            search_name="GenesByRNASeqFoldChange",
            resolved_params=bound({"fold_change": StringValue(value="1")}),
            param_display_names={"fold_change": "log2 fold change >="},
        )

        assert _fold([rnaseq], requested="2-fold").status is ConstraintStatus.GROUNDED
