"""The graded distance between two strategy shapes.

A boolean verdict reports an operator swap and an unrelated search the same
way. These are the numbers that separate them.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from pathfinder.evals.distance import (
    COMBINE_LABEL,
    ComparisonNode,
    SignatureSyntaxError,
    parameter_fidelity,
    search_names,
    strategy_distance,
    tree_from_ast,
    tree_from_signature,
)

_UNION_FIRST = "((GenesByText UNION GenesByGoTerm) INTERSECT GenesByTaxon)"
_INTERSECT_FIRST = "((GenesByText INTERSECT GenesByGoTerm) INTERSECT GenesByTaxon)"
_UNRELATED = "GenesByLocation"


class TestTheSignatureParser:
    def test_a_bare_name_is_one_leaf(self) -> None:
        tree = tree_from_signature("GenesByText")

        assert tree == ComparisonNode(search_name="GenesByText")

    def test_a_combine_carries_its_operator_and_both_inputs(self) -> None:
        tree = tree_from_signature("(GenesByText UNION GenesByGoTerm)")

        assert tree.search_name == COMBINE_LABEL
        assert tree.operator == "UNION"
        assert [child.search_name for child in tree.children] == [
            "GenesByText",
            "GenesByGoTerm",
        ]

    def test_a_transform_wraps_its_input(self) -> None:
        tree = tree_from_signature("GenesByOrthologs(GenesByText)")

        assert tree.search_name == "GenesByOrthologs"
        assert [child.search_name for child in tree.children] == ["GenesByText"]

    def test_the_signature_a_five_node_build_writes_round_trips(self) -> None:
        assert search_names(tree_from_signature(_UNION_FIRST)) == [
            "GenesByText",
            "GenesByGoTerm",
            "GenesByTaxon",
        ]

    def test_an_unclosed_combine_is_refused(self) -> None:
        with pytest.raises(SignatureSyntaxError, match="unclosed"):
            tree_from_signature("(GenesByText UNION GenesByGoTerm")

    def test_trailing_text_is_refused(self) -> None:
        with pytest.raises(SignatureSyntaxError, match="trailing"):
            tree_from_signature("GenesByText GenesByGoTerm")


class TestTheDecomposition:
    def test_the_same_shape_scores_zero_on_every_layer(self) -> None:
        tree = tree_from_signature(_UNION_FIRST)

        distance = strategy_distance(tree, tree)

        assert distance.topology == 0.0
        assert distance.search_selection == 0.0
        assert distance.labelled == 0.0

    def test_an_operator_swap_keeps_the_topology_and_the_searches(self) -> None:
        """The card's first row: one operator away must not read as far away."""
        distance = strategy_distance(
            tree_from_signature(_UNION_FIRST),
            tree_from_signature(_INTERSECT_FIRST),
        )

        assert distance.topology == 0.0
        assert distance.search_selection == 0.0
        assert distance.labelled == 0.06

    def test_a_strategy_that_shares_no_search_is_far(self) -> None:
        """The card's second row: nothing in common must not read as one edit."""
        distance = strategy_distance(
            tree_from_signature(_UNION_FIRST),
            tree_from_signature(_UNRELATED),
        )

        assert distance.topology == 0.8
        assert distance.search_selection == 1.0
        assert distance.labelled == 1.0

    def test_the_operator_swap_is_nearer_than_the_unrelated_search(self) -> None:
        near = strategy_distance(
            tree_from_signature(_UNION_FIRST),
            tree_from_signature(_INTERSECT_FIRST),
        )
        far = strategy_distance(
            tree_from_signature(_UNION_FIRST),
            tree_from_signature(_UNRELATED),
        )

        assert near.labelled < far.labelled
        assert near.topology < far.topology

    def test_one_missing_leaf_scores_between_the_two(self) -> None:
        distance = strategy_distance(
            tree_from_signature(_UNION_FIRST),
            tree_from_signature("(GenesByText INTERSECT GenesByTaxon)"),
        )

        assert distance.topology == 0.4
        assert distance.search_selection == pytest.approx(1 / 3, abs=1e-4)
        assert 0.0 < distance.labelled < 1.0


def _leaf(search_name: str, **parameters: str) -> StrategyStepNode:
    return StrategyStepNode(
        search_name=search_name,
        parameters={
            name: SinglePickValue(value=value) for name, value in parameters.items()
        },
    )


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


class TestParameterFidelity:
    def test_a_signature_alone_states_no_parameters(self) -> None:
        assert (
            parameter_fidelity(
                tree_from_signature(_UNION_FIRST),
                tree_from_signature(_UNION_FIRST),
            )
            is None
        )

    def test_matching_values_on_the_aligned_search_score_one(self) -> None:
        want = tree_from_ast(_ast(_leaf("GenesByText", text_expression="kinase")))
        got = tree_from_ast(_ast(_leaf("GenesByText", text_expression="kinase")))

        assert parameter_fidelity(want, got) == 1.0

    def test_a_changed_value_on_the_aligned_search_scores_zero(self) -> None:
        want = tree_from_ast(_ast(_leaf("GenesByText", text_expression="kinase")))
        got = tree_from_ast(_ast(_leaf("GenesByText", text_expression="protease")))

        assert parameter_fidelity(want, got) == 0.0

    def test_half_the_values_agreeing_scores_half(self) -> None:
        want = tree_from_ast(
            _ast(_leaf("GenesByText", text_expression="kinase", organism="pf"))
        )
        got = tree_from_ast(
            _ast(_leaf("GenesByText", text_expression="kinase", organism="pv"))
        )

        assert parameter_fidelity(want, got) == 0.5

    def test_a_multi_pick_value_compares_regardless_of_order(self) -> None:
        first = StrategyStepNode(
            search_name="GenesByGoTerm",
            parameters={"evidence": MultiPickValue(values=["Curated", "Computed"])},
        )
        second = StrategyStepNode(
            search_name="GenesByGoTerm",
            parameters={"evidence": MultiPickValue(values=["Computed", "Curated"])},
        )

        assert (
            parameter_fidelity(tree_from_ast(_ast(first)), tree_from_ast(_ast(second)))
            == 1.0
        )


class TestTheTreeOfABuiltStrategy:
    def test_a_combine_signs_under_one_label_whatever_wdk_calls_it(self) -> None:
        root = StrategyStepNode(
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.UNION,
            primary_input=_leaf("GenesByText"),
            secondary_input=_leaf("GenesByGoTerm"),
        )

        tree = tree_from_ast(_ast(root))

        assert tree.search_name == COMBINE_LABEL
        assert tree.operator == "UNION"
        assert search_names(tree) == ["GenesByText", "GenesByGoTerm"]

    def test_a_built_strategy_and_its_signature_score_zero_apart(self) -> None:
        root = StrategyStepNode(
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                operator=CombineOp.UNION,
                primary_input=_leaf("GenesByText", text_expression="kinase"),
                secondary_input=_leaf("GenesByGoTerm"),
            ),
            secondary_input=_leaf("GenesByTaxon"),
        )

        distance = strategy_distance(
            tree_from_signature(_UNION_FIRST),
            tree_from_ast(_ast(root)),
        )

        assert distance.topology == 0.0
        assert distance.search_selection == 0.0
        assert distance.labelled == 0.0
