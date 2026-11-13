from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START
from langgraph.graph.state import CompiledStateGraph

from strategist.ai.graph.builder import build_strategist_graph
from strategist.ai.graph.runtime import Context
from strategist.ai.graph.state import PipelineState


@pytest.fixture
def compiled_graph() -> CompiledStateGraph[
    PipelineState,
    Context,
    PipelineState,
    PipelineState,
]:
    return build_strategist_graph(checkpointer=InMemorySaver())


def test_graph_has_the_route_and_both_agents(
    compiled_graph: CompiledStateGraph[
        PipelineState,
        Context,
        PipelineState,
        PipelineState,
    ],
) -> None:
    nodes = set(compiled_graph.get_graph().nodes.keys())
    expected = {START, END, "route", "lead", "explore", "finalize_turn"}
    assert expected.issubset(nodes), nodes


def test_the_graph_starts_at_the_route(
    compiled_graph: CompiledStateGraph[
        PipelineState,
        Context,
        PipelineState,
        PipelineState,
    ],
) -> None:
    edges = compiled_graph.get_graph().edges
    targets_from_start = {e.target for e in edges if e.source == START}
    assert targets_from_start == {"route"}


def test_compiled_graph_records_state_schema_with_checkpointer(
    compiled_graph: CompiledStateGraph[
        PipelineState,
        Context,
        PipelineState,
        PipelineState,
    ],
) -> None:
    assert compiled_graph.checkpointer is not None
    assert getattr(compiled_graph, "context_schema", None) is not None
