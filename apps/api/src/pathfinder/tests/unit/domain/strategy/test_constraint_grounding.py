"""Grounding a stated requirement against the strategy that was actually built."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.constraint_grounding import ground_constraints
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    SignificanceValue,
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
            criteria=[
                Criterion(id="c1", text="fold change", search_name=_MICROARRAY_SEARCH)
            ],
            marks=_MICROARRAY_MARKS,
        ),
    )
    return grounded


class TestGroundingAgainstTheBuiltSearch:
    def test_a_threshold_the_search_does_not_link_is_not_verified(self) -> None:
        grounded = _ground_on_microarray(
            _explicit(
                ConstraintKind.STATISTICAL_THRESHOLD,
                "adjusted p <= 0.05",
                "significance",
            ).model_copy(update={"value": SignificanceValue(at_most=0.05)})
        )

        assert (grounded.status, grounded.realized_value, is_blocking(grounded)) == (
            ConstraintStatus.GROUNDED,
            None,
            False,
        )


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
