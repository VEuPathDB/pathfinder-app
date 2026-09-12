"""The traversal surface: the bottom-up fold, the walk order, the partition
into the three step kinds, and the parent lookup.

WDK's step tree is a binary tree, so every walk splits into three disjoint sets
whose union is the whole tree, and an input is always placed before the step
that consumes it.
"""

from __future__ import annotations

from hypothesis import given
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyStepNode,
    flatten_tree,
    fold,
    leaves,
    parent_of,
    walk,
)

from ._builders import FAST_PROFILE, strategy_trees

_TREES = strategy_trees()


def _tree() -> StrategyStepNode:
    """``orthologs(a) INTERSECT b``."""
    return StrategyStepNode(
        id="c",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="t",
            search_name="GenesByOrthologs",
            primary_input=StrategyStepNode(id="a", search_name="GenesByText"),
        ),
        secondary_input=StrategyStepNode(id="b", search_name="GenesByTaxon"),
    )


def _render(node: StrategyStepNode, inputs: list[str]) -> str:
    return f"{node.id}[{','.join(inputs)}]"


def combines(root: StrategyStepNode) -> list[StrategyStepNode]:
    return [node for node in walk(root) if len(node.inputs()) == 2]


class TestTheFold:
    """A node sees its inputs already folded, in slot order. An empty slot is
    absent from the list, so the length states the kind."""

    def test_a_search_sees_no_inputs(self) -> None:
        assert fold(StrategyStepNode(id="a", search_name="x"), _render) == "a[]"

    def test_a_transform_sees_its_one_input(self) -> None:
        root = StrategyStepNode(
            id="t",
            search_name="GenesByOrthologs",
            primary_input=StrategyStepNode(id="a", search_name="x"),
        )

        assert fold(root, _render) == "t[a[]]"

    def test_a_combine_sees_both_inputs_in_slot_order(self) -> None:
        assert fold(_tree(), _render) == "c[t[a[]],b[]]"

    def test_every_node_is_folded_exactly_once(self) -> None:
        seen: list[str] = []

        def _record(node: StrategyStepNode, inputs: list[None]) -> None:
            del inputs
            seen.append(node.id)

        fold(_tree(), _record)

        assert seen == [step.id for step in walk(_tree())]

    def test_the_fold_never_mutates_the_tree(self) -> None:
        root = _tree()
        before = root.model_dump(by_alias=True, mode="json")

        fold(root, lambda node, inputs: node.id)

        assert root.model_dump(by_alias=True, mode="json") == before


class TestThePartition:
    @FAST_PROFILE
    @given(_TREES)
    def test_leaves_and_combines_never_overlap(self, root: StrategyStepNode) -> None:
        leaf_ids = {node.id for node in leaves(root)}
        combine_ids = {node.id for node in combines(root)}

        assert leaf_ids & combine_ids == set()

    @FAST_PROFILE
    @given(_TREES)
    def test_the_three_kinds_cover_the_whole_tree(self, root: StrategyStepNode) -> None:
        every = {node.id for node in walk(root)}
        leaf_ids = {node.id for node in leaves(root)}
        combine_ids = {node.id for node in combines(root)}
        transform_ids = {
            node.id for node in walk(root) if node.infer_kind() == "transform"
        }

        assert leaf_ids | combine_ids | transform_ids == every
        assert len(leaf_ids) + len(combine_ids) + len(transform_ids) == len(every)

    @FAST_PROFILE
    @given(_TREES)
    def test_the_two_shapes_agree_on_which_step_is_which(
        self, root: StrategyStepNode
    ) -> None:
        """The flat map states the kind; the tree infers it from the slots."""
        steps = flatten_tree(root)

        assert {node.id for node in leaves(root)} == {
            step.id for step in steps.values() if step.kind is StepKind.SEARCH
        }
        assert {node.id for node in combines(root)} == {
            step.id for step in steps.values() if step.kind is StepKind.COMBINE
        }

    @FAST_PROFILE
    @given(_TREES)
    def test_a_leaf_consumes_nothing_and_a_combine_consumes_both_slots(
        self, root: StrategyStepNode
    ) -> None:
        assert [node.input_ids() for node in leaves(root)] == [[]] * len(leaves(root))
        assert [node.input_ids() for node in combines(root)] == [
            [node.primary_input_id, node.secondary_input_id] for node in combines(root)
        ]


class TestTheWalkOrder:
    @FAST_PROFILE
    @given(_TREES)
    def test_every_input_comes_before_the_step_that_consumes_it(
        self, root: StrategyStepNode
    ) -> None:
        order = [node.id for node in walk(root)]

        for node in walk(root):
            for input_id in node.input_ids():
                assert order.index(input_id) < order.index(node.id)

    @FAST_PROFILE
    @given(_TREES)
    def test_the_walk_visits_every_step_once(self, root: StrategyStepNode) -> None:
        walked = [node.id for node in walk(root)]

        assert sorted(walked) == sorted(flatten_tree(root))
        assert len(walked) == len(set(walked))


class TestTheParentLookup:
    @FAST_PROFILE
    @given(_TREES)
    def test_every_step_but_the_root_names_the_slot_it_occupies(
        self, root: StrategyStepNode
    ) -> None:
        steps = flatten_tree(root)
        slots = {
            input_id: (step.id, slot)
            for step in steps.values()
            for slot, input_id in (
                ("primary", step.primary_input_id),
                ("secondary", step.secondary_input_id),
            )
            if input_id is not None
        }

        found = {
            step_id: (pair[0].id, pair[1])
            for step_id in steps
            if (pair := parent_of(step_id, steps)) is not None
        }

        assert found == slots
        assert parent_of(root.id, steps) is None
