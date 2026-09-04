"""Grounding a stated requirement against the strategy that was actually built."""

from __future__ import annotations

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
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.ops import CombineOp

# The realized facts of a single microarray fold-change leaf.
_MICROARRAY_SEARCH = (
    "GenesByMicroarrayaaegLVP_AGWG_microarrayExpression_GSE22339_male_vs_female_RSRC"
)
_MICROARRAY_FACTS: dict[str, list[str] | set[str] | dict[str, str]] = {
    "search_names": [_MICROARRAY_SEARCH],
    "param_names": {"fold_change"},
    "param_values": {"fold_change": "2"},
}


def _explicit(kind: ConstraintKind, value: str, label: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
        label=label,
    )


class TestGroundingAgainstTheBuiltSearch:
    def test_rnaseq_requested_but_microarray_used_is_substituted(self) -> None:
        [grounded] = ground_constraints(
            [_explicit(ConstraintKind.DATA_TYPE, "RNA-Seq", "data type")],
            **_MICROARRAY_FACTS,
        )

        assert grounded.status is ConstraintStatus.SUBSTITUTED
        assert grounded.realized_value == "microarray"

    def test_pvalue_threshold_with_no_significance_param_is_ungroundable(self) -> None:
        [grounded] = ground_constraints(
            [
                _explicit(
                    ConstraintKind.STATISTICAL_THRESHOLD,
                    "adjusted p <= 0.05",
                    "significance",
                )
            ],
            **_MICROARRAY_FACTS,
        )

        assert grounded.status is ConstraintStatus.UNGROUNDABLE
        assert grounded.realized_value is None

    def test_fold_change_present_is_grounded(self) -> None:
        [grounded] = ground_constraints(
            [
                Constraint(
                    kind=ConstraintKind.FOLD_CHANGE,
                    requested_value="2",
                    label="fold change",
                )
            ],
            **_MICROARRAY_FACTS,
        )

        assert grounded.status is ConstraintStatus.GROUNDED


def _percentile(requested: str) -> Constraint:
    return _explicit(ConstraintKind.PERCENTILE, requested, "expression percentile")


def _ground_percentile(
    requested: str, param_name: str, bound: str
) -> GroundedConstraint:
    [grounded] = ground_constraints(
        [_percentile(requested)],
        search_names=[_MICROARRAY_SEARCH],
        param_names={param_name},
        param_values={param_name: bound},
    )
    return grounded


class TestThePercentileBound:
    def test_a_percentile_bound_that_means_the_stated_share_is_grounded(self) -> None:
        grounded = _ground_percentile("top 10%", "min_expression_percentile", "90")

        assert grounded.status is ConstraintStatus.GROUNDED
        assert grounded.realized_value == "90"

    def test_a_percentile_bound_that_means_another_share_is_substituted(self) -> None:
        """A min percentile of 80 is the top 20 percent, not the top 10."""
        grounded = _ground_percentile("top 10%", "min_expression_percentile", "80")

        assert grounded.status is ConstraintStatus.SUBSTITUTED
        assert grounded.realized_value == "80"
        assert grounded.note == "bound 80 means top 20%"
        assert is_blocking(grounded) is True

    def test_a_bottom_share_reads_the_max_percentile_bound(self) -> None:
        grounded = _ground_percentile(
            "bottom 25 percent", "max_expression_percentile", "25"
        )

        assert grounded.status is ConstraintStatus.GROUNDED

    def test_a_percentile_constraint_without_a_percentile_param_is_ungroundable(
        self,
    ) -> None:
        grounded = _ground_percentile("top 10%", "fold_change", "2")

        assert grounded.status is ConstraintStatus.UNGROUNDABLE
        assert grounded.note == "no percentile parameter in the strategy"

    def test_a_percentile_request_without_a_direction_is_ungroundable(self) -> None:
        grounded = _ground_percentile("10%", "min_expression_percentile", "90")

        assert grounded.status is ConstraintStatus.UNGROUNDABLE
        assert grounded.note == "the requested share and direction could not be read"


_MS_CRITERION = Criterion(
    id="c_ms",
    text="trophozoite mass spectrometry evidence",
    search_name="GenesByMassSpec",
)
_DERISI_CRITERION = Criterion(
    id="c_derisi",
    text="DeRisi timecourse expression",
    search_name="GenesByRNASeqEvidence",
)


def _joined(operator: CombineOp) -> SpecStructure:
    return SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=operator,
            inputs=[
                StructureNode(kind="leaf", criterion_id="c_ms"),
                StructureNode(kind="leaf", criterion_id="c_derisi"),
            ],
        )
    )


def _ground_combination(
    value: str, structure: SpecStructure | None
) -> GroundedConstraint:
    [grounded] = ground_constraints(
        [_explicit(ConstraintKind.COMBINATION, value, "how the evidence combines")],
        search_names=["GenesByMassSpec", "GenesByRNASeqEvidence"],
        param_names=set(),
        param_values={},
        structure=structure,
        criteria=[_MS_CRITERION, _DERISI_CRITERION],
    )
    return grounded


class TestGroundingACombination:
    def test_a_stated_or_the_tree_unions_is_grounded(self) -> None:
        grounded = _ground_combination(
            "mass spectrometry evidence OR DeRisi expression", _joined(CombineOp.UNION)
        )

        assert grounded.status is ConstraintStatus.GROUNDED
        assert grounded.realized_value == "UNION"

    def test_a_stated_or_the_tree_intersects_is_ungroundable(self) -> None:
        grounded = _ground_combination(
            "mass spectrometry evidence OR DeRisi expression",
            _joined(CombineOp.INTERSECT),
        )

        assert grounded.status is ConstraintStatus.UNGROUNDABLE
        assert "UNION" in grounded.note
        assert "INTERSECT" in grounded.note
        assert is_blocking(grounded) is True

    def test_a_combination_naming_no_criterion_abstains(self) -> None:
        grounded = _ground_combination(
            "proteomics OR microscopy", _joined(CombineOp.INTERSECT)
        )

        assert grounded.status is ConstraintStatus.GROUNDED
        assert "abstained" in grounded.note

    def test_a_combination_without_a_structure_abstains(self) -> None:
        grounded = _ground_combination(
            "mass spectrometry evidence OR DeRisi expression", None
        )

        assert grounded.status is ConstraintStatus.GROUNDED
        assert "abstained" in grounded.note
