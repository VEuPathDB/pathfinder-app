"""A stated combination of three or more terms, read at every combine.

The meeting node alone leaves room for a branch that joins two of the named
criteria with the other operator.
"""

from __future__ import annotations

from hypothesis import given, strategies
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.combination_check import (
    combination_violation,
    first_combination_violation,
)
from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)

from ._builders import spec_joined, spec_leaf, spec_transform

_OR_THREE = CombinationRequest(
    operator="OR",
    terms=["kinases", "mass spectrometry evidence", "DeRisi expression"],
)
_THREE_IDS = ["c_kinase", "c_ms", "c_derisi"]
_OR_FOUR = CombinationRequest(
    operator="OR", terms=[*_OR_THREE.terms, "phyletic profile"]
)
_FOUR_IDS = [*_THREE_IDS, "c_phyletic"]


def _violation(request: CombinationRequest, ids: list[str], root: StructureNode) -> str:
    """Why the tree breaks the request, empty when it honors it."""
    return combination_violation(request, ids, SpecStructure(root=root)) or ""


def _operators(node: StructureNode) -> list[CombineOp]:
    """Every combine operator the tree carries."""
    found = [] if node.operator is None else [node.operator]
    for child in node.inputs:
        found.extend(_operators(child))
    return found


@strategies.composite
def _binary_trees(draw: strategies.DrawFn, ids: list[str]) -> StructureNode:
    """A binary tree holding each of these criteria once, operators drawn.

    A criterion sits at a plain leaf, under a transform the statement does not
    name, or at a transform the statement names over an input it does not.
    Each shape brings that one criterion, so the verdict is the same.
    """
    if len(ids) == 1:
        shape = draw(strategies.sampled_from(["leaf", "transform", "named"]))
        if shape == "transform":
            return spec_transform(f"t_{ids[0]}", spec_leaf(ids[0]))
        if shape == "named":
            return spec_transform(ids[0], spec_leaf(f"u_{ids[0]}"))
        return spec_leaf(ids[0])
    cut = draw(strategies.integers(min_value=1, max_value=len(ids) - 1))
    operator = draw(strategies.sampled_from([CombineOp.UNION, CombineOp.INTERSECT]))
    return spec_joined(
        operator, draw(_binary_trees(ids[:cut])), draw(_binary_trees(ids[cut:]))
    )


class TestThreeOrMoreTerms:
    def test_an_or_refuses_an_intersect_under_the_meeting_union(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_joined(CombineOp.INTERSECT, spec_leaf("c_ms"), spec_leaf("c_derisi")),
        )

        violation = _violation(_OR_THREE, _THREE_IDS, root)

        assert "must be UNION" in violation
        assert "joins two of them at INTERSECT" in violation

    def test_an_or_accepts_a_union_of_unions(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_joined(CombineOp.UNION, spec_leaf("c_ms"), spec_leaf("c_derisi")),
        )

        assert _violation(_OR_THREE, _THREE_IDS, root) == ""

    def test_an_or_accepts_one_union_over_three_inputs(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_leaf("c_ms"),
            spec_leaf("c_derisi"),
        )

        assert _violation(_OR_THREE, _THREE_IDS, root) == ""

    def test_an_intersect_two_levels_under_the_meeting_node_is_read(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_joined(
                CombineOp.UNION,
                spec_leaf("c_ms"),
                spec_joined(
                    CombineOp.INTERSECT,
                    spec_leaf("c_derisi"),
                    spec_leaf("c_phyletic"),
                ),
            ),
        )

        assert "joins two of them at INTERSECT" in _violation(_OR_FOUR, _FOUR_IDS, root)

    def test_a_combine_mixing_in_an_unnamed_criterion_is_not_refused(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_joined(
                CombineOp.UNION,
                spec_leaf("c_ms"),
                spec_joined(
                    CombineOp.INTERSECT, spec_leaf("c_derisi"), spec_leaf("c_other")
                ),
            ),
        )

        assert _violation(_OR_THREE, _THREE_IDS, root) == ""

    def test_an_and_refuses_a_union_under_the_meeting_intersect(self) -> None:
        request = CombinationRequest(operator="AND", terms=_OR_THREE.terms)
        root = spec_joined(
            CombineOp.INTERSECT,
            spec_leaf("c_kinase"),
            spec_joined(CombineOp.UNION, spec_leaf("c_ms"), spec_leaf("c_derisi")),
        )

        violation = _violation(request, _THREE_IDS, root)

        assert "must be INTERSECT" in violation
        assert "joins two of them at UNION" in violation

    def test_the_breach_of_a_three_term_request_names_its_operator(self) -> None:
        criteria = [
            Criterion(id="c_kinase", text="kinases by molecular function"),
            Criterion(id="c_ms", text="trophozoite mass spectrometry evidence"),
            Criterion(id="c_derisi", text="DeRisi timecourse expression"),
        ]
        structure = SpecStructure(
            root=spec_joined(
                CombineOp.UNION,
                spec_leaf("c_kinase"),
                spec_joined(
                    CombineOp.INTERSECT, spec_leaf("c_ms"), spec_leaf("c_derisi")
                ),
            )
        )

        breach = first_combination_violation(
            [
                Constraint(
                    kind=ConstraintKind.COMBINATION,
                    requested_value=_OR_THREE.expression,
                    label="how the evidence combines",
                    source=ConstraintSource.USER_EXPLICIT,
                )
            ],
            criteria,
            structure,
        )

        assert breach is not None
        assert breach.required is CombineOp.UNION
        assert "joins two of them at INTERSECT" in breach.message

    @given(tree=_binary_trees(_FOUR_IDS))
    def test_an_or_holds_exactly_when_every_combine_unions(
        self, tree: StructureNode
    ) -> None:
        violation = _violation(_OR_FOUR, _FOUR_IDS, tree)

        assert (violation == "") == all(
            op is CombineOp.UNION for op in _operators(tree)
        )


class TestTransformsAreTransparent:
    """A transform the statement does not name carries its input's criterion."""

    def test_an_or_refuses_an_intersect_over_a_transformed_criterion(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_joined(
                CombineOp.INTERSECT,
                spec_transform("c_orthologs", spec_leaf("c_ms")),
                spec_leaf("c_derisi"),
            ),
        )

        violation = _violation(_OR_THREE, _THREE_IDS, root)

        assert "must be UNION" in violation
        assert "joins two of them at INTERSECT" in violation

    def test_a_transform_over_a_mixed_combine_is_not_refused(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_joined(
                CombineOp.UNION,
                spec_leaf("c_ms"),
                spec_transform(
                    "c_orthologs",
                    spec_joined(
                        CombineOp.INTERSECT,
                        spec_leaf("c_derisi"),
                        spec_leaf("c_other"),
                    ),
                ),
            ),
        )

        assert _violation(_OR_THREE, _THREE_IDS, root) == ""

    def test_an_or_accepts_a_union_over_a_transformed_criterion(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_joined(
                CombineOp.UNION,
                spec_transform("c_orthologs", spec_leaf("c_ms")),
                spec_leaf("c_derisi"),
            ),
        )

        assert _violation(_OR_THREE, _THREE_IDS, root) == ""


_NAMED_TRANSFORM_CRITERIA = [
    Criterion(
        id="c_kinase",
        text="protein kinases",
        search_name="GenesByMolecularFunction",
    ),
    Criterion(
        id="c_ms",
        text="trophozoite mass spectrometry evidence",
        search_name="GenesByMassSpec",
    ),
    Criterion(
        id="c_orth", text="orthologs in P. vivax", search_name="GenesByOrthologs"
    ),
    Criterion(
        id="c_derisi", text="DeRisi timecourse expression", search_name="GenesByRNASeq"
    ),
]
_OR_NAMED_TRANSFORM = CombinationRequest(
    operator="OR",
    terms=["protein kinases", "vivax orthologs", "DeRisi expression"],
)


class TestAStatementThatNamesTheTransform:
    """A transform the statement names stands for its whole input."""

    def test_an_or_refuses_an_intersect_when_the_statement_names_the_transform(
        self,
    ) -> None:
        structure = SpecStructure(
            root=spec_joined(
                CombineOp.UNION,
                spec_leaf("c_kinase"),
                spec_joined(
                    CombineOp.INTERSECT,
                    spec_transform("c_orth", spec_leaf("c_ms")),
                    spec_leaf("c_derisi"),
                ),
            )
        )

        breach = first_combination_violation(
            [
                Constraint(
                    kind=ConstraintKind.COMBINATION,
                    requested_value=_OR_NAMED_TRANSFORM.expression,
                    label="how the evidence combines",
                    source=ConstraintSource.USER_EXPLICIT,
                )
            ],
            _NAMED_TRANSFORM_CRITERIA,
            structure,
        )

        assert breach is not None
        assert breach.required is CombineOp.UNION
        assert "must be UNION" in breach.message
        assert "joins two of them at INTERSECT" in breach.message

    def test_an_or_accepts_a_union_when_the_statement_names_the_transform(self) -> None:
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_joined(
                CombineOp.UNION,
                spec_transform("c_orth", spec_leaf("c_ms")),
                spec_leaf("c_derisi"),
            ),
        )

        violation = _violation(
            _OR_NAMED_TRANSFORM, ["c_kinase", "c_orth", "c_derisi"], root
        )

        assert violation == ""

    def test_an_or_naming_a_transform_and_its_input_meets_at_no_combine(self) -> None:
        """A named transform hides its input, so the input meets the union nowhere."""
        request = CombinationRequest(
            operator="OR",
            terms=["protein kinases", "mass spectrometry evidence", "vivax orthologs"],
        )
        root = spec_joined(
            CombineOp.UNION,
            spec_leaf("c_kinase"),
            spec_transform("c_orth", spec_leaf("c_ms")),
        )

        violation = _violation(request, ["c_kinase", "c_ms", "c_orth"], root)

        assert "must meet at UNION" in violation
        assert "no combine node" in violation
