"""Shared error payloads, graph and step lookup, and result models for strategy tools."""

import json
from typing import Annotated

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import StrategyStep
from veupathdb.domain.strategy.operations import GraphOperation
from veupathdb.domain.strategy.session import StrategyGraph, StrategySession
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.errors import ValidationError
from veupathdb_mcp.tool_errors import ToolErrorPayload, tool_error

from pathfinder.domain.strategy.stated_shape import placeholder_names
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.strategies.schemas import StepResponse


def _reject_placeholder_steps(root: StrategyStepNode) -> StrategyStepNode:
    found = placeholder_names(root)
    if found:
        msg = (
            f"{', '.join(found)}: a placeholder, not a WDK search. Every step "
            f"names the search it runs, so name that search or leave the step "
            f"out of the tree."
        )
        raise ValueError(msg)
    return root


StepTreePayload = Annotated[StrategyStepNode, AfterValidator(_reject_placeholder_steps)]
"""A step tree the model authored, refused while it holds a placeholder name."""


def _step_tree_of(op: GraphOperation) -> StrategyStepNode | None:
    """The step tree an operation carries, or None when it carries none."""
    if op.kind == "addLeaf":
        return op.step
    if op.kind == "addCombine":
        return op.step
    if op.kind == "addTransform":
        return op.step
    if op.kind == "replaceSubtree":
        return op.subtree
    if op.kind == "replaceStrategy":
        return op.root
    return None


def _reject_placeholder_operations(op: GraphOperation) -> GraphOperation:
    tree = _step_tree_of(op)
    if tree is not None:
        _reject_placeholder_steps(tree)
    return op


OperationPayload = Annotated[
    GraphOperation, AfterValidator(_reject_placeholder_operations)
]
"""One graph operation the model authored, held to the same name rule."""


class GraphEdge(CamelModel):
    """One edge in a strategy graph snapshot. The snapshot is a tool result that the
    model reads, not a wire event, so the shape follows the WDK slot names."""

    source_id: str
    target_id: str
    kind: str


class GraphSnapshotContent(CamelModel):
    """A strategy graph snapshot that step mutation results carry."""

    graph_id: str | None = None
    graph_name: str | None = None
    record_type: str | None = None
    name: str | None = None
    description: str | None = None
    root_step_id: str | None = None
    steps: list[JSONObject] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    strategy_ast: StrategyAst | None = None


class _ValidationErrorEntry(BaseModel):
    """One entry in a validation error list."""

    model_config = ConfigDict(extra="ignore")
    context: dict[str, JsonValue] = Field(default_factory=dict)


class ContextStrategyAstPayload(CamelModel):
    """The strategy tree plus the graph identity that a tool returns with it."""

    graph_id: str
    graph_name: str | None = None
    strategy_ast: StrategyAst
    record_type: str
    name: str | None = None
    description: str | None = None


class StepOkResponse(CamelModel):
    """The response a successful step mutation returns."""

    ok: bool = True
    step: StepResponse
    graph_id: str
    graph_name: str | None = None
    record_type: str | None = None
    name: str | None = None
    description: str | None = None
    strategy_ast: StrategyAst | None = None
    graph_snapshot: GraphSnapshotContent


def get_graph(session: StrategySession, graph_id: str | None) -> StrategyGraph | None:
    """Returns the graph this id addresses, or the active graph when none is given.

    The id is PathFinder's graph id or the VEuPathDB strategy id the graph was
    pushed to. An unknown id returns None; the active graph is never
    substituted for it.
    """
    graph = session.get_graph(graph_id)
    if graph is not None or graph_id is None:
        return graph
    return _graph_of_wdk_strategy(session, graph_id)


def _graph_of_wdk_strategy(
    session: StrategySession, strategy_id: str
) -> StrategyGraph | None:
    """The graph pushed to this VEuPathDB strategy, or None."""
    sync_state = session.sync_state
    if sync_state is None or sync_state.wdk_strategy_id is None:
        return None
    if strategy_id.strip() != str(sync_state.wdk_strategy_id):
        return None
    return session.graph


def graph_not_found(graph_id: str | None) -> ToolErrorPayload:
    if graph_id:
        return tool_error(
            ErrorCode.NOT_FOUND,
            "No strategy has that id. Pass the graph id, the VEuPathDB "
            "strategy id, or nothing at all for the active strategy.",
            graphId=graph_id,
        )
    return tool_error(
        ErrorCode.NOT_FOUND, "Graph not found. Provide a graphId.", graphId=graph_id
    )


def step_not_found(step_id: str) -> ToolErrorPayload:
    """Builds the error payload for a missing step."""
    return tool_error(
        ErrorCode.STEP_NOT_FOUND, f"Step not found: {step_id}", stepId=step_id
    )


def get_graph_and_step(
    session: StrategySession, graph_id: str | None, step_id: str
) -> tuple[StrategyGraph, StrategyStep] | ToolErrorPayload:
    """Looks up the graph and the step. A failure returns an error payload that the
    caller can return without change."""
    graph = get_graph(session, graph_id)
    if not graph:
        return graph_not_found(graph_id)
    step = graph.get_step(step_id)
    if not step:
        return step_not_found(step_id)
    return graph, step


def validation_error_payload(
    exc: ValidationError, **context: JsonValue
) -> ToolErrorPayload:
    details: JSONObject = {}
    if exc.detail:
        details["detail"] = exc.detail
    if exc.errors is not None:
        details["errors"] = exc.errors
        for raw_error in exc.errors:
            parsed = _ValidationErrorEntry.model_validate(raw_error)
            context.update({k: v for k, v in parsed.context.items() if v is not None})
    details.update({k: v for k, v in context.items() if v is not None})
    return tool_error(ErrorCode.VALIDATION_ERROR, exc.title, **details)


def validation_model_retry(
    exc: ValidationError,
    **context: JsonValue,
) -> ModelRetry:
    payload = validation_error_payload(exc, **context).model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )
    return ModelRetry(json.dumps(payload))


def is_placeholder_name(name: str | None) -> bool:
    if not name:
        return True
    return name.strip().lower() in {
        "draft graph",
        "draft strategy",
        "draft",
        "new conversation",
    }
