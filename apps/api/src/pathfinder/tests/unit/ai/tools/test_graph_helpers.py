"""The AST the model is shown names the main tree as its root.

The rest of a mid-edit canvas travels in ``detached_roots``.
"""

from __future__ import annotations

from assistant_core.persistence.repositories.conversation import (
    DEFAULT_CONVERSATION_NAME,
)
from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.ai.tools.standalone.graph_helpers import (
    build_context_strategy_ast,
    build_step_response,
    count_summary,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.fixtures.builders import add_step_to_graph


def _leaf(step_id: str) -> StrategyStep:
    return StrategyStep(id=step_id, kind=StepKind.SEARCH, search_name="GenesByText")


def _graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "kinases", "plasmodb")
    graph.record_type = "transcript"
    return graph


def _with_a_pair_and_a_stray() -> StrategyGraph:
    """``(a INTERSECT b)`` beside a leaf nobody consumes."""
    graph = _graph()
    add_step_to_graph(graph, _leaf("a"))
    add_step_to_graph(graph, _leaf("b"))
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
    add_step_to_graph(graph, _leaf("stray"))
    return graph


class TestTheContextPayloadUsesThatRule:
    def test_one_root_is_the_payload_root(self) -> None:
        graph = _graph()
        add_step_to_graph(graph, _leaf("a"))
        session = StrategySession("plasmodb")
        session.add_graph(graph)
        session.sync_state = WDKSyncState()

        payload = build_context_strategy_ast(session, graph)

        assert payload is not None
        assert payload.strategy_ast.root.id == "a"

    def test_several_roots_take_the_main_tree_and_carry_the_rest_detached(
        self,
    ) -> None:
        graph = _with_a_pair_and_a_stray()
        session = StrategySession("plasmodb")
        session.add_graph(graph)
        session.sync_state = WDKSyncState()

        payload = build_context_strategy_ast(session, graph)

        assert payload is not None
        assert payload.strategy_ast.root.id == "c"
        assert [d.id for d in payload.strategy_ast.detached_roots] == ["stray"]

    def test_no_steps_is_no_payload(self) -> None:
        graph = _graph()
        session = StrategySession("plasmodb")
        session.add_graph(graph)
        session.sync_state = WDKSyncState()

        assert build_context_strategy_ast(session, graph) is None

        add_step_to_graph(graph, _leaf("a"))
        payload = build_context_strategy_ast(session, graph)
        assert payload is not None
        assert payload.strategy_ast.root.id == "a"

    def test_no_record_type_is_no_payload(self) -> None:
        graph = StrategyGraph("g1", "kinases", "plasmodb")
        add_step_to_graph(graph, _leaf("a"))
        session = StrategySession("plasmodb")
        session.add_graph(graph)
        session.sync_state = WDKSyncState()

        assert build_context_strategy_ast(session, graph) is None

        graph.record_type = "transcript"
        payload = build_context_strategy_ast(session, graph)
        assert payload is not None
        assert payload.strategy_ast.root.id == "a"

    def test_a_graph_with_no_name_yet_keeps_it(self) -> None:
        """Only a push names a graph that has no name yet."""
        graph = StrategyGraph("g1", DEFAULT_CONVERSATION_NAME, "plasmodb")
        graph.record_type = "transcript"
        add_step_to_graph(graph, _leaf("a"))
        session = StrategySession("plasmodb")
        session.add_graph(graph)
        session.sync_state = WDKSyncState()

        payload = build_context_strategy_ast(session, graph)

        assert payload is not None
        assert (payload.name, graph.name) == (
            DEFAULT_CONVERSATION_NAME,
            DEFAULT_CONVERSATION_NAME,
        )


def test_a_step_wdk_refused_reports_no_estimated_size() -> None:
    """A refused push leaves the previous search on the WDK step and its size."""
    graph = _graph()
    step = _leaf("a")
    add_step_to_graph(graph, step)
    sync_state = WDKSyncState(
        wdk_step_ids={"a": 440432473},
        step_counts={"a": 1282},
        wdk_push_errors={"a": "422 profileset_generic: Invalid value"},
    )

    response = build_step_response(graph, step, sync_state)

    assert response.estimated_size is None
    assert response.wdk_push_error == "422 profileset_generic: Invalid value"


def test_an_unnamed_combine_is_answered_under_its_operators_name() -> None:
    graph = _with_a_pair_and_a_stray()

    response = build_step_response(graph, graph.steps["c"])

    assert response.display_name == "Intersect"


class TestTheStrategyLineNamesWhatItCounted:
    """``count_summary`` states a size in the records the strategy holds."""

    def test_one_step_and_one_gene_are_not_written_as_plurals(self) -> None:
        line, status = count_summary(1, 1, "transcript")

        assert line == "1 step, 1 gene"
        assert status == "ok"

    def test_a_transcript_answer_is_counted_in_genes(self) -> None:
        line, status = count_summary(1, 479, "transcript")

        assert line == "1 step, 479 genes"
        assert status == "ok"

    def test_the_noun_is_the_record_type_the_strategy_holds(self) -> None:
        line, status = count_summary(3, 16, "pathway")

        assert line == "3 steps, 16 pathways"
        assert status == "ok"

    def test_a_large_count_is_written_for_a_reader(self) -> None:
        line, _ = count_summary(2, 9_667, "transcript")

        assert line == "2 steps, 9,667 genes"

    def test_a_strategy_that_holds_nothing_reports_empty(self) -> None:
        line, status = count_summary(2, 0, "transcript")

        assert line == "2 steps, 0 genes"
        assert status == "empty"

    def test_a_count_nobody_measured_is_not_spent_as_a_zero(self) -> None:
        line, status = count_summary(1, None, "transcript")

        assert line == "1 step, count not available"
        assert status == "warn"

    def test_a_graph_with_no_record_type_still_names_what_it_counted(self) -> None:
        line, _ = count_summary(1, 5, None)

        assert line == "1 step, 5 records"
