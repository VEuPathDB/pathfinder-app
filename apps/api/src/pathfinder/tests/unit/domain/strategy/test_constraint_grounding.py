"""Grounding a stated requirement against the strategy that was actually built."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

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
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.realized_spec import RealizedSpec

# The realized facts of a single microarray fold-change leaf, and the assay
# vectorbase's dataset record names for its search.
_MICROARRAY_SEARCH = (
    "GenesByMicroarrayaaegLVP_AGWG_microarrayExpression_GSE22339_male_vs_female_RSRC"
)
_MICROARRAY_MARKS = DataMarks(searches={_MICROARRAY_SEARCH: "DNA Microarray Assay"})


def _explicit(kind: ConstraintKind, value: str, label: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
        label=label,
    )


def _ground_on_microarray(constraint: Constraint) -> GroundedConstraint:
    [grounded] = ground_constraints(
        [constraint],
        RealizedSpec(
            search_names=[_MICROARRAY_SEARCH],
            param_names=frozenset({"fold_change"}),
            param_values={"fold_change": "2"},
            criteria=[
                Criterion(id="c1", text="fold change", search_name=_MICROARRAY_SEARCH)
            ],
            marks=_MICROARRAY_MARKS,
        ),
    )
    return grounded


class TestGroundingAgainstTheBuiltSearch:
    def test_rnaseq_requested_but_microarray_used_is_substituted(self) -> None:
        grounded = _ground_on_microarray(
            _explicit(ConstraintKind.DATA_TYPE, "RNA-Seq", "data type")
        )

        assert grounded.status is ConstraintStatus.SUBSTITUTED
        assert grounded.realized_value == "microarray"

    def test_pvalue_threshold_with_no_significance_param_is_ungroundable(self) -> None:
        grounded = _ground_on_microarray(
            _explicit(
                ConstraintKind.STATISTICAL_THRESHOLD,
                "adjusted p <= 0.05",
                "significance",
            )
        )

        assert grounded.status is ConstraintStatus.UNGROUNDABLE
        assert grounded.realized_value is None

    def test_fold_change_present_is_grounded(self) -> None:
        grounded = _ground_on_microarray(
            Constraint(
                kind=ConstraintKind.FOLD_CHANGE,
                requested_value="2",
                label="fold change",
            )
        )

        assert grounded.status is ConstraintStatus.GROUNDED


def _percentile(requested: str) -> Constraint:
    return _explicit(ConstraintKind.PERCENTILE, requested, "expression percentile")


def _ground_percentile(
    requested: str, param_name: str, bound: str
) -> GroundedConstraint:
    [grounded] = ground_constraints(
        [_percentile(requested)],
        RealizedSpec(
            search_names=[_MICROARRAY_SEARCH],
            param_names=frozenset({param_name}),
            param_values={param_name: bound},
        ),
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


_HELD_COMBINATION = Constraint(
    id="r_comb",
    kind=ConstraintKind.COMBINATION,
    requested_value="mass spectrometry evidence OR DeRisi expression",
    source=ConstraintSource.USER_EXPLICIT,
    label="how the evidence combines",
)
_LINK = [RequirementLink(requirement="r_comb")]


def _linked(cid: str, search: str, role: CriterionRole = "filter") -> Criterion:
    return Criterion(id=cid, text=cid, search_name=search, role=role, answers=_LINK)


_MS_CRITERION = _linked("c_ms", "GenesByMassSpec")
_DERISI_CRITERION = _linked("c_derisi", "GenesByRNASeqEvidence")
_ORTHOLOG_CRITERION = _linked("c_ortho", "GenesByOrthologs", "transform")
_EXCLUDE_CRITERION = _linked("c_crypto", "GenesByOrthologPhyleticPattern", "exclude")


def _joined(operator: CombineOp, *inputs: StructureNode) -> SpecStructure:
    return SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=operator,
            inputs=list(inputs)
            or [
                StructureNode(kind="leaf", criterion_id="c_ms"),
                StructureNode(kind="leaf", criterion_id="c_derisi"),
            ],
        )
    )


def _ground_held(
    structure: SpecStructure | None, *criteria: Criterion
) -> GroundedConstraint:
    [grounded] = ground_constraints(
        [_HELD_COMBINATION],
        RealizedSpec(
            search_names=[c.search_name for c in criteria],
            param_values={},
            structure=structure,
            criteria=list(criteria),
        ),
    )
    return grounded


class TestGroundingAHeldCombination:
    def test_its_linked_criteria_meet_at_the_operator_the_tree_holds(self) -> None:
        grounded = _ground_held(
            _joined(CombineOp.INTERSECT), _MS_CRITERION, _DERISI_CRITERION
        )

        assert (grounded.status, grounded.realized_value, grounded.note) == (
            ConstraintStatus.GROUNDED,
            None,
            (
                "the combination check abstained: the criteria that link it meet "
                "at INTERSECT, and that combine is read against the researcher's "
                "words"
            ),
        )
        assert is_blocking(grounded) is False

    def test_a_combination_no_criterion_links_abstains(self) -> None:
        unlinked = [
            c.model_copy(update={"answers": []})
            for c in (_MS_CRITERION, _DERISI_CRITERION)
        ]

        grounded = _ground_held(_joined(CombineOp.UNION), *unlinked)

        assert (grounded.status, grounded.note) == (
            ConstraintStatus.GROUNDED,
            "the combination check abstained: no criterion links it",
        )

    def test_a_combination_without_a_structure_abstains(self) -> None:
        grounded = _ground_held(None, _MS_CRITERION, _DERISI_CRITERION)

        assert "abstained" in grounded.note

    def test_a_transform_over_a_linked_criterion_is_on_the_path(self) -> None:
        mapped = StructureNode(
            kind="transform",
            criterion_id="c_ortho",
            inputs=[StructureNode(kind="leaf", criterion_id="c_ms")],
        )

        grounded = _ground_held(
            _joined(
                CombineOp.INTERSECT,
                mapped,
                StructureNode(kind="leaf", criterion_id="c_derisi"),
            ),
            _MS_CRITERION,
            _DERISI_CRITERION,
            _ORTHOLOG_CRITERION,
        )

        assert "meet at INTERSECT" in grounded.note

    def test_a_transform_the_tree_leaves_out_abstains(self) -> None:
        grounded = _ground_held(
            _joined(CombineOp.INTERSECT),
            _MS_CRITERION,
            _DERISI_CRITERION,
            _ORTHOLOG_CRITERION,
        )

        assert "abstained" in grounded.note

    def test_an_exclusion_subtracted_from_the_members_is_read(self) -> None:
        grounded = _ground_held(
            _joined(
                CombineOp.MINUS,
                _joined(CombineOp.INTERSECT).root,
                StructureNode(kind="leaf", criterion_id="c_crypto"),
            ),
            _MS_CRITERION,
            _DERISI_CRITERION,
            _EXCLUDE_CRITERION,
        )

        assert "meet at INTERSECT" in grounded.note

    def test_an_exclusion_the_tree_keeps_abstains(self) -> None:
        grounded = _ground_held(
            _joined(
                CombineOp.INTERSECT,
                _joined(CombineOp.INTERSECT).root,
                StructureNode(kind="leaf", criterion_id="c_crypto"),
            ),
            _MS_CRITERION,
            _DERISI_CRITERION,
            _EXCLUDE_CRITERION,
        )

        assert "abstained" in grounded.note

    def test_one_linked_member_says_why_it_abstains(self) -> None:
        grounded = _ground_held(
            _joined(
                CombineOp.MINUS,
                StructureNode(kind="leaf", criterion_id="c_ms"),
                StructureNode(kind="leaf", criterion_id="c_crypto"),
            ),
            _MS_CRITERION,
            _EXCLUDE_CRITERION,
        )

        assert "fewer than two" in grounded.note


def _toxodb_export() -> Criterion:
    """The toxodb step an exported EDA analysis selects, at log2 0.585."""
    return Criterion(
        id="step_818600c8",
        text="up in bradyzoites over tachyzoites",
        analysis=AnalysisBinding(
            dataset_id="DS_toxo_bradyzoite",
            effect_direction="upOnly",
            effect_size_threshold=0.585,
            significance_threshold=0.05,
            words="bradyzoite over tachyzoite, log2 fold change 0.585, p 0.05",
        ),
    )


class TestAnAnalysisStatesItsCuts:
    def test_a_fold_change_an_exported_analysis_cuts_at_is_grounded(self) -> None:
        [grounded] = ground_constraints(
            [_explicit(ConstraintKind.FOLD_CHANGE, "1.5-fold", "fold change")],
            RealizedSpec(
                search_names=[],
                param_values={},
                criteria=[_toxodb_export()],
            ),
        )

        assert grounded.status is ConstraintStatus.GROUNDED

    def test_a_significance_an_exported_analysis_cuts_at_is_grounded(self) -> None:
        [grounded] = ground_constraints(
            [_explicit(ConstraintKind.STATISTICAL_THRESHOLD, "p 0.05", "p value")],
            RealizedSpec(
                search_names=[],
                param_values={},
                criteria=[_toxodb_export()],
            ),
        )

        assert grounded.status is ConstraintStatus.GROUNDED

    def test_a_fold_change_no_search_and_no_analysis_states_is_ungroundable(
        self,
    ) -> None:
        [grounded] = ground_constraints(
            [_explicit(ConstraintKind.FOLD_CHANGE, "1.5-fold", "fold change")],
            RealizedSpec(
                search_names=["GenesWithSignalPeptide"],
                param_names=frozenset({"organism"}),
                param_values={},
            ),
        )

        assert grounded.status is ConstraintStatus.UNGROUNDABLE
