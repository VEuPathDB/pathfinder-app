"""The researcher's words for each step reach the store, the load and the wire."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import (
    StepKind,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.tools.standalone.graph_helpers import build_step_response
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.persistence.models import PersistedStrategyGraph
from pathfinder.services.strategies import spec_build
from pathfinder.services.strategies.commit import graph_labels, restore_graph
from pathfinder.services.strategies.schemas import step_response_from_strategy_ast
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.sync_state import WDKSyncState

_WORDS = "genes with a predicted GPI anchor"


def _leaf(step_id: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByExportPrediction",
        display_name="Exported Protein",
    )


def _stored(step_id: str) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=_leaf(step_id),
        metadata=StepWords(criterion_texts={step_id: _WORDS}).model_dump(by_alias=True),
    )


def _graph_of(step_id: str) -> StrategyGraph:
    graph = StrategyGraph("g1", "GPI", "plasmodb")
    graph.steps.update(flatten_tree(_leaf(step_id)))
    graph.recompute_roots()
    return graph


def test_a_loaded_strategy_holds_the_words_it_stored() -> None:
    session = build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(
            id=str(uuid4()), name="GPI", strategy_ast=_stored("step_a")
        ),
    )

    assert session.graph is not None
    assert session.graph.words.criterion_texts == {"step_a": _WORDS}


def test_a_stored_step_answers_with_its_title_and_its_words() -> None:
    ast = _stored("step_a")

    response = step_response_from_strategy_ast(ast, ast.root)

    assert (response.display_name, response.criterion_text) == (
        "Exported Protein",
        _WORDS,
    )


def test_a_live_step_answers_with_its_words() -> None:
    graph = _graph_of("step_a")
    graph.note_words(StepWords(criterion_texts={"step_a": _WORDS}))

    response = build_step_response(graph, graph.steps["step_a"])

    assert (response.display_name, response.criterion_text) == (
        "Exported Protein",
        _WORDS,
    )


def test_a_step_no_criterion_stated_carries_no_words() -> None:
    ast = StrategyAst(record_type="transcript", root=_leaf("step_a"))

    response = step_response_from_strategy_ast(ast, ast.root)

    assert (response.display_name, response.criterion_text) == (
        "Exported Protein",
        None,
    )


def test_a_build_takes_the_words_for_the_steps_it_writes() -> None:
    graph = StrategyGraph("g1", "GPI", "plasmodb")
    graph.note_words(StepWords(criterion_texts={"step_old": "old words"}))

    spec_build._replace_graph_contents(
        graph,
        _leaf("step_new"),
        sync_state=WDKSyncState(),
        description=None,
        step_words=StepWords(
            criterion_texts={"step_new": _WORDS, "c_unbuilt": "never built"}
        ),
    )

    assert graph.words.criterion_texts == {"step_new": _WORDS}


def test_a_rolled_back_batch_puts_the_words_back() -> None:
    graph = _graph_of("step_a")
    graph.note_words(StepWords(criterion_texts={"step_a": _WORDS}))
    entry = graph_labels(graph)
    old = graph.to_strategy_ast()

    graph.note_words(StepWords(criterion_texts={"step_a": "a batch that is refused"}))
    restore_graph(graph, old, entry)

    assert graph.words.criterion_texts == {"step_a": _WORDS}
    assert graph.steps["step_a"].kind is StepKind.SEARCH
