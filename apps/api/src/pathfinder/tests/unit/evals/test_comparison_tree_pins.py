"""The shapes the eval comparison tree and the structure signature produce.

One representative tree per node kind, plus the half-wired combine the canvas
can hold. These values do not change when the traversal moves to the owner.
"""

from __future__ import annotations

from veupathdb.domain.parameters.values import MultiPickValue, StringValue
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.evals.distance import COMBINE_LABEL, tree_from_ast
from pathfinder.evals.scoring import structure_signature


def _leaf(name: str, step_id: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=name)


def _representative_root() -> StrategyStepNode:
    """A combine over a transform-wrapped leaf and a parameterised leaf."""
    return StrategyStepNode(
        id="c",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="t",
            search_name="GenesByOrthologs",
            primary_input=StrategyStepNode(
                id="a",
                search_name="GenesByText",
                parameters={"text_expression": StringValue(value="kinase")},
            ),
        ),
        secondary_input=StrategyStepNode(
            id="b",
            search_name="GenesByTaxon",
            parameters={"organism": MultiPickValue(values=["Pf3D7", "Pberghei"])},
        ),
    )


def _half_wired_combine() -> StrategyStepNode:
    """A combine that lost its secondary input keeps the sentinel name."""
    return StrategyStepNode(
        id="c",
        search_name=COMBINE_SEARCH_NAME,
        primary_input=_leaf("GenesByText", "a"),
    )


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


class TestTheComparisonTree:
    def test_a_combine_is_labelled_and_keeps_its_inputs_in_slot_order(self) -> None:
        tree = tree_from_ast(_ast(_representative_root()))

        assert tree.search_name == COMBINE_LABEL
        assert tree.operator == "INTERSECT"
        assert [child.search_name for child in tree.children] == [
            "GenesByOrthologs",
            "GenesByTaxon",
        ]

    def test_a_transform_carries_its_single_input(self) -> None:
        tree = tree_from_ast(_ast(_representative_root()))

        transform = tree.children[0]
        assert transform.operator is None
        assert [child.search_name for child in transform.children] == ["GenesByText"]

    def test_a_leaf_carries_its_parameters_as_canonical_text(self) -> None:
        tree = tree_from_ast(_ast(_representative_root()))

        assert tree.children[0].children[0].parameters == {"text_expression": "kinase"}
        assert tree.children[1].parameters == {"organism": "Pberghei,Pf3D7"}

    def test_a_leaf_root_is_one_childless_node(self) -> None:
        tree = tree_from_ast(_ast(_leaf("GenesByTaxon", "a")))

        assert tree.search_name == "GenesByTaxon"
        assert tree.children == ()

    def test_a_half_wired_combine_is_still_labelled_a_combine(self) -> None:
        tree = tree_from_ast(_ast(_half_wired_combine()))

        assert tree.search_name == COMBINE_LABEL
        assert [child.search_name for child in tree.children] == ["GenesByText"]

    def test_detached_roots_are_not_part_of_the_comparison(self) -> None:
        ast = StrategyAst(
            record_type="transcript",
            root=_leaf("GenesByTaxon", "a"),
            detached_roots=[_leaf("GenesByText", "z")],
        )

        tree = tree_from_ast(ast)

        assert tree.search_name == "GenesByTaxon"
        assert tree.children == ()


class TestTheStructureSignature:
    def test_it_writes_the_operator_between_the_two_branches(self) -> None:
        assert (
            structure_signature(_ast(_representative_root()))
            == "(GenesByOrthologs(GenesByText) INTERSECT GenesByTaxon)"
        )

    def test_a_leaf_root_is_its_own_search_name(self) -> None:
        assert structure_signature(_ast(_leaf("GenesByTaxon", "a"))) == "GenesByTaxon"

    def test_a_half_wired_combine_writes_a_question_mark_per_gap(self) -> None:
        assert structure_signature(_ast(_half_wired_combine())) == "(GenesByText ? ?)"

    def test_a_transform_root_wraps_its_input(self) -> None:
        root = StrategyStepNode(
            id="t",
            search_name="GenesByOrthologs",
            primary_input=_leaf("GenesByText", "a"),
        )

        assert structure_signature(_ast(root)) == "GenesByOrthologs(GenesByText)"
