from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from pathfinder.ai.graph.lead_node import make_lead_node
from pathfinder.ai.graph.nodes import finalize_turn_node
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.pre_turn import pathfinder_pre_turn

__all__ = ["build_pathfinder_graph"]


def build_pathfinder_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[PipelineState, Context, PipelineState, PipelineState]:
    """PathFinder's turn graph: the Lead runs the turn, then the turn closes."""
    graph: StateGraph[PipelineState, Context, PipelineState, PipelineState] = (
        StateGraph(PipelineState, context_schema=Context)
    )
    graph.add_node(
        "lead",
        make_lead_node(pre_turn=pathfinder_pre_turn, build_agent=build_lead_agent),
    )
    graph.add_node("finalize_turn", finalize_turn_node)
    graph.add_edge(START, "lead")
    return graph.compile(checkpointer=checkpointer)
