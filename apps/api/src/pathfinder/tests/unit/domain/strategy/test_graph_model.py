"""Separating step data from tree structure has to be lossless.

WDK carries structure and data separately (``stepTree`` holds only step ids,
``steps`` holds the data), and this is the conversion to that shape. Nothing
may be lost in either direction, so the round trip is asserted over generated
trees rather than a handful of examples.
"""

from __future__ import annotations

from hypothesis import given

from pathfinder.domain.parameters.values import StringValue
from pathfinder.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from pathfinder.domain.strategy.graph_model import (
    StepKind,
    StrategyStep,
    flatten_tree,
    is_computable,
    pushable_root_id,
    rebuild_tree,
    runs_a_wdk_search,
    wdk_search_name,
)
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.tree import root_ids, subtree_ids
from pathfinder.tests.fixtures.builders import add_step_to_graph

from ._builders import FAST_PROFILE, combine, strategy_trees

_TREES = strategy_trees()
_BOOLEAN_QUESTION = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


def _taxon(step_id: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name="GenesByTaxon")


def _wired_combine() -> dict[str, StrategyStep]:
    """``a INTERSECT b``, flattened."""
    return flatten_tree(combine("c", _taxon("a"), _taxon("b")))


def _flat_combine(**overrides: object) -> StrategyStep:
    base: dict[str, object] = {
        "id": "c",
        "kind": StepKind.COMBINE,
        "primary_input_id": "a",
        "secondary_input_id": "b",
        "operator": CombineOp.INTERSECT,
    }
    return StrategyStep.model_validate(base | overrides)


def _pushable(step_id: str, steps: dict[str, StrategyStep]) -> str:
    """The step WDK is given, empty when nothing is computable."""
    return pushable_root_id(step_id, steps) or ""


class TestRoundTrip:
    @FAST_PROFILE
    @given(_TREES)
    def test_a_tree_survives_the_split_and_rejoin(self, node: StrategyStepNode) -> None:
        assert rebuild_tree(node.id, flatten_tree(node)) == node

    @FAST_PROFILE
    @given(_TREES)
    def test_every_step_appears_exactly_once_in_the_map(
        self, node: StrategyStepNode
    ) -> None:
        steps = flatten_tree(node)
        ids = subtree_ids(node.id, steps)

        assert sorted(ids) == sorted(steps)
        assert len(ids) == len(set(ids))

    @FAST_PROFILE
    @given(_TREES)
    def test_the_data_map_holds_no_structure(self, node: StrategyStepNode) -> None:
        """A step no longer contains its inputs, so editing one cannot mutate
        the tree behind another view's back."""
        for step in flatten_tree(node).values():
            fields = type(step).model_fields
            assert "primary_input" not in fields
            assert "secondary_input" not in fields

    @FAST_PROFILE
    @given(_TREES)
    def test_the_tree_has_exactly_one_root(self, node: StrategyStepNode) -> None:
        assert root_ids(flatten_tree(node)) == {node.id}


class TestKindIsExplicit:
    def test_a_leaf_is_a_search(self) -> None:
        assert flatten_tree(_taxon("a"))["a"].kind is StepKind.SEARCH

    def test_one_input_is_a_transform(self) -> None:
        node = StrategyStepNode(
            id="t", search_name="orthologs", primary_input=_taxon("a")
        )

        assert flatten_tree(node)["t"].kind is StepKind.TRANSFORM

    def test_two_inputs_are_a_combine(self) -> None:
        assert _wired_combine()["c"].kind is StepKind.COMBINE

    def test_the_combine_sentinel_does_not_survive_as_a_search_name(self) -> None:
        """``__combine__`` exists only because kind had to be guessed from
        structure. With kind explicit the placeholder has no job."""
        step = _wired_combine()["c"]

        assert (step.kind, step.search_name) == (StepKind.COMBINE, None)

    def test_rebuilding_restores_the_sentinel_for_the_persisted_shape(self) -> None:
        """``searchName`` is required on the persisted node, so the projection
        back to the nested shape puts the placeholder back."""
        assert rebuild_tree("c", _wired_combine()).search_name == COMBINE_SEARCH_NAME

    def test_the_flat_step_of_a_sentinel_combine_has_no_search_name(self) -> None:
        node = StrategyStepNode(
            id="c",
            primary_input=StrategyStepNode(id="a", search_name="a"),
            secondary_input=StrategyStepNode(id="b", search_name="b"),
            operator=CombineOp.INTERSECT,
        )
        step = flatten_tree(node)["c"]

        assert (step.kind, step.search_name) == (StepKind.COMBINE, None)

    def test_rebuilding_puts_the_sentinel_back(self) -> None:
        steps = {
            "a": StrategyStep(id="a", kind=StepKind.SEARCH, search_name="a"),
            "b": StrategyStep(id="b", kind=StepKind.SEARCH, search_name="b"),
            "c": _flat_combine(),
        }

        assert rebuild_tree("c", steps).search_name == COMBINE_SEARCH_NAME


class TestComputability:
    """A combine needs two inputs and an operator to mean anything.

    Detaching an edge leaves one behind deliberately, and WDK cannot compute it
    in that state, so the projection walks past it rather than pushing a step
    that will be rejected.
    """

    def test_a_wired_combine_is_computable(self) -> None:
        assert is_computable(_wired_combine()["c"]) is True

    def test_a_combine_missing_its_secondary_is_not(self) -> None:
        steps = _wired_combine()
        steps["c"].secondary_input_id = None

        assert is_computable(steps["c"]) is False

    def test_a_combine_without_an_operator_is_not(self) -> None:
        steps = _wired_combine()
        steps["c"].operator = None

        assert is_computable(steps["c"]) is False

    def test_a_leaf_is_always_computable(self) -> None:
        assert is_computable(flatten_tree(_taxon("a"))["a"]) is True

    def test_the_pushable_root_walks_past_a_half_wired_combine(self) -> None:
        """What WDK is given after an edge is cut: the surviving branch."""
        steps = _wired_combine()
        steps["c"].secondary_input_id = None
        steps["c"].operator = None

        assert _pushable("c", steps) == "a"

    def test_a_fully_wired_root_is_its_own_pushable_root(self) -> None:
        assert _pushable("c", _wired_combine()) == "c"

    def test_a_combine_with_nothing_left_has_no_pushable_root(self) -> None:
        steps = _wired_combine()
        steps["c"].primary_input_id = None
        steps["c"].secondary_input_id = None
        steps["c"].operator = None

        assert _pushable("c", steps) == ""


class TestWhatEachReaderActuallyAsks:
    def test_a_combine_reports_the_sentinel_as_its_outward_name(self) -> None:
        assert wdk_search_name(_flat_combine()) == COMBINE_SEARCH_NAME

    def test_a_combine_wdk_named_reports_that_name(self) -> None:
        assert wdk_search_name(_flat_combine(search_name=_BOOLEAN_QUESTION)) == (
            _BOOLEAN_QUESTION
        )

    def test_a_search_reports_its_own_name(self) -> None:
        step = StrategyStep(
            id="a",
            kind=StepKind.SEARCH,
            search_name="GenesByText",
            parameters={"text_expression": StringValue(value="kinase")},
        )

        assert wdk_search_name(step) == "GenesByText"

    def test_only_a_named_step_runs_a_wdk_search(self) -> None:
        named = StrategyStep(id="a", kind=StepKind.SEARCH, search_name="GenesByText")
        unnamed = StrategyStep(id="b", kind=StepKind.SEARCH, search_name=None)

        assert [runs_a_wdk_search(s) for s in (named, _flat_combine(), unnamed)] == [
            True,
            False,
            False,
        ]

    def test_a_transform_that_only_carries_the_sentinel_reports_it(self) -> None:
        """A combine that lost a slot round-trips as a transform, and its name
        is still the sentinel, so it still names no runnable search."""
        node = StrategyStepNode(
            id="c",
            search_name=COMBINE_SEARCH_NAME,
            primary_input=StrategyStepNode(id="a", search_name="a"),
        )

        step = flatten_tree(node)["c"]

        assert step.kind is StepKind.TRANSFORM
        assert wdk_search_name(step) == COMBINE_SEARCH_NAME
        assert runs_a_wdk_search(step) is False


def _text_step(step_id: str) -> StrategyStep:
    return StrategyStep(id=step_id, kind=StepKind.SEARCH, search_name="GenesByText")


def _empty_graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "kinases", "plasmodb")
    graph.record_type = "transcript"
    return graph


def _root_of(graph: StrategyGraph) -> str:
    """The graph's addressed root, empty when it has none."""
    return graph.primary_root_id() or ""


def _with_a_pair_and_a_stray() -> StrategyGraph:
    """``(a INTERSECT b)`` beside a leaf nobody consumes."""
    graph = _empty_graph()
    add_step_to_graph(graph, _text_step("a"))
    add_step_to_graph(graph, _text_step("b"))
    add_step_to_graph(
        graph,
        StrategyStep(
            id="c",
            kind=StepKind.COMBINE,
            primary_input_id="a",
            secondary_input_id="b",
            operator=CombineOp.INTERSECT,
        ),
    )
    add_step_to_graph(graph, _text_step("stray"))
    return graph


class TestThePrimaryRoot:
    """A mid-edit canvas holds several roots. One rule picks the main tree."""

    def test_an_empty_graph_has_none(self) -> None:
        assert _root_of(_empty_graph()) == ""

    def test_one_root_is_the_root(self) -> None:
        graph = _empty_graph()
        add_step_to_graph(graph, _text_step("a"))

        assert graph.primary_root_id() == "a"

    def test_the_largest_subtree_wins(self) -> None:
        assert _with_a_pair_and_a_stray().primary_root_id() == "c"

    def test_the_last_added_root_does_not_win_by_being_last(self) -> None:
        graph = _with_a_pair_and_a_stray()

        assert graph.last_step_id == "stray"
        assert graph.primary_root_id() == "c"

    def test_a_tie_goes_to_the_step_added_first(self) -> None:
        graph = _empty_graph()
        add_step_to_graph(graph, _text_step("first"))
        add_step_to_graph(graph, _text_step("second"))

        assert graph.primary_root_id() == "first"
