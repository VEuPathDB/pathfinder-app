"""The structural invariants of ``StrategyStepNode`` and ``StrategyAst``.

Hypothesis exercises walk order and kind inference over generated trees;
the negative cases pin the validators so a silent loosening fails loudly.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from pydantic import ValidationError
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.ops import ColocationParams, CombineOp
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.domain.strategy.tree import walk

from ._builders import ANY_TREE, PROFILE

_BOOLEAN_QUESTION = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


def _count_nodes(node: StrategyStepNode) -> int:
    total = 1
    if node.primary_input is not None:
        total += _count_nodes(node.primary_input)
    if node.secondary_input is not None:
        total += _count_nodes(node.secondary_input)
    return total


def _pair(left: str = "a", right: str = "b") -> tuple[StrategyStepNode, ...]:
    return StrategyStepNode(search_name=left), StrategyStepNode(search_name=right)


@PROFILE
@given(ANY_TREE)
def test_walk_step_tree_is_post_order_and_unique(root: StrategyStepNode) -> None:
    steps = walk(root)
    ids = [s.id for s in steps]
    assert len(ids) == len(set(ids)), f"walk returned duplicate ids: {ids}"
    assert steps[-1] is root, "root must be visited last in post-order traversal"
    assert len(steps) == _count_nodes(root)
    seen: set[str] = set()
    for node in steps:
        if node.primary_input is not None:
            assert node.primary_input.id in seen, (
                "primary_input must be visited before parent"
            )
        if node.secondary_input is not None:
            assert node.secondary_input.id in seen, (
                "secondary_input must be visited before parent"
            )
        seen.add(node.id)


@PROFILE
@given(ANY_TREE)
def test_infer_kind_matches_structure(root: StrategyStepNode) -> None:
    for node in walk(root):
        kind = node.infer_kind()
        if node.primary_input is not None and node.secondary_input is not None:
            assert kind == "combine"
        elif node.primary_input is not None:
            assert kind == "transform"
        else:
            assert kind == "search"


@PROFILE
@given(ANY_TREE)
def test_combine_nodes_carry_combine_search_name(root: StrategyStepNode) -> None:
    for node in walk(root):
        if node.primary_input is not None and node.secondary_input is not None:
            assert node.search_name == COMBINE_SEARCH_NAME


class TestTheValidators:
    def test_secondary_without_primary_is_rejected(self) -> None:
        leaf = StrategyStepNode(search_name="a")
        with pytest.raises(
            ValidationError, match="secondaryInput requires primaryInput"
        ):
            StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                secondary_input=leaf,
                operator=CombineOp.INTERSECT,
            )

    def test_combine_without_operator_is_rejected(self) -> None:
        a, b = _pair()
        with pytest.raises(ValidationError, match="operator is required"):
            StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME, primary_input=a, secondary_input=b
            )

    def test_combine_with_same_step_id_is_rejected(self) -> None:
        a = StrategyStepNode(search_name="a", id="step_dup")
        b = StrategyStepNode(search_name="b", id="step_dup")
        with pytest.raises(
            ValidationError, match="cannot use the same step on both inputs"
        ):
            StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                primary_input=a,
                secondary_input=b,
                operator=CombineOp.INTERSECT,
            )

    def test_the_same_node_on_both_inputs_is_rejected(self) -> None:
        leaf = StrategyStepNode(search_name="GenesByTaxon", display_name="Step A")
        with pytest.raises(
            ValidationError, match="cannot use the same step on both inputs"
        ):
            StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                display_name="Self-union",
                primary_input=leaf,
                secondary_input=leaf,
                operator=CombineOp.UNION,
            )

    def test_colocate_without_colocation_params_is_rejected(self) -> None:
        a, b = _pair()
        with pytest.raises(ValidationError, match="colocationParams is required"):
            StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                primary_input=a,
                secondary_input=b,
                operator=CombineOp.COLOCATE,
            )

    def test_colocation_params_without_colocate_is_rejected(self) -> None:
        a, b = _pair()
        with pytest.raises(ValidationError, match="colocationParams is only allowed"):
            StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                primary_input=a,
                secondary_input=b,
                operator=CombineOp.UNION,
                colocation_params=ColocationParams(),
            )

    def test_expanded_strategy_id_outside_combine_is_rejected(self) -> None:
        with pytest.raises(
            ValidationError, match="expandedStrategyId is only valid on combine"
        ):
            StrategyStepNode(
                search_name="a", expanded_strategy_id=42, expanded_name="saved-1"
            )

    def test_expanded_strategy_id_without_name_is_rejected(self) -> None:
        a, b = _pair()
        with pytest.raises(ValidationError, match="expandedName is required"):
            StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                primary_input=a,
                secondary_input=b,
                operator=CombineOp.INTERSECT,
                expanded_strategy_id=42,
            )

    def test_a_single_input_node_with_no_name_is_refused(self) -> None:
        """One input is a transform, and a transform names its own search."""
        with pytest.raises(ValidationError, match="searchName"):
            StrategyStepNode(primary_input=StrategyStepNode(search_name="a"))

    def test_strategy_ast_rejects_duplicate_ids_across_tree(self) -> None:
        leaf_x = StrategyStepNode(search_name="a", id="dup")
        leaf_y = StrategyStepNode(search_name="b", id="dup")
        root = StrategyStepNode(
            search_name=COMBINE_SEARCH_NAME,
            primary_input=leaf_x,
            secondary_input=StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                primary_input=leaf_y,
                secondary_input=StrategyStepNode(search_name="c"),
                operator=CombineOp.INTERSECT,
            ),
            operator=CombineOp.UNION,
        )
        with pytest.raises(ValidationError, match="duplicate step ids"):
            StrategyAst(record_type="transcript", root=root)


class TestTheDisplayLabel:
    def test_combine_default_search_name_is_injected(self) -> None:
        a, b = _pair()
        node = StrategyStepNode(
            primary_input=a, secondary_input=b, operator=CombineOp.INTERSECT
        )

        assert node.search_name == COMBINE_SEARCH_NAME

    def test_display_label_combine_never_leaks_sentinel(self) -> None:
        a, b = _pair()
        node = StrategyStepNode(
            primary_input=a, secondary_input=b, operator=CombineOp.INTERSECT
        )

        assert node.search_name == COMBINE_SEARCH_NAME
        assert node.display_label == "Combine"

    def test_display_label_prefers_explicit_display_name(self) -> None:
        a, b = _pair()
        node = StrategyStepNode(
            primary_input=a,
            secondary_input=b,
            operator=CombineOp.UNION,
            display_name="My combine",
        )

        assert node.display_label == "My combine"

    def test_a_named_combine_keeps_its_name(self) -> None:
        a, b = _pair()
        node = StrategyStepNode(
            search_name=_BOOLEAN_QUESTION,
            primary_input=a,
            secondary_input=b,
            operator=CombineOp.INTERSECT,
        )

        assert node.search_name == _BOOLEAN_QUESTION

    def test_display_label_search_falls_back_to_search_name(self) -> None:
        assert StrategyStepNode(search_name="GenesByText").display_label == (
            "GenesByText"
        )
        labelled = StrategyStepNode(
            search_name="GenesByText", display_name="Text search"
        )
        assert labelled.display_label == "Text search"
