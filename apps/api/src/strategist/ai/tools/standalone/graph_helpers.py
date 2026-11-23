"""Graph snapshot building, step serialization, and strategy naming.

Functions that operate on ``StrategyGraph`` to produce serialized
responses and context payloads for AI tool results.
"""

from assistant_core.graph.stream_events import ToolSummaryStatus
from assistant_core.graph.tool_summary import count_noun
from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy import StrategyStep

from strategist.ai.tools.standalone._validation_helpers import (
    ContextStrategyAstPayload,
    GraphEdge,
    GraphSnapshotContent,
    StepOkResponse,
)
from strategist.domain.strategy.explain import explain_operation
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.domain.strategy.types import SyncStateProtocol
from strategist.services.strategies.schemas import StepResponse, step_response

# ---------------------------------------------------------------------------
# Strategy naming
# ---------------------------------------------------------------------------


def derive_strategy_name(
    record_type: str | None,
    root_step: StrategyStep,
) -> str:
    base = None
    kind = root_step.kind.value
    if kind in {"search", "transform"}:
        base = root_step.display_name or root_step.search_name
    elif kind == "combine":
        if root_step.operator is not None:
            base = root_step.display_name or explain_operation(root_step.operator)
        else:
            base = root_step.display_name
    base = (base or "").strip()
    if not base:
        base = f"{record_type.title()} strategy" if record_type else "Strategy"
    if record_type and record_type.lower() not in base.lower():
        base = f"{record_type.title()} - {base}"
    return base[:120]


# ---------------------------------------------------------------------------
# Step serialization
# ---------------------------------------------------------------------------


def count_summary(
    step_count: int, records: int | None, record_type: str | None
) -> tuple[str, ToolSummaryStatus]:
    """The one line every strategy surface reports its size with.

    A count nobody measured is reported as missing, never spent as a zero.
    """
    steps = count_noun(step_count, "step")
    if records is None:
        return f"{steps}, count not available", "warn"
    return f"{steps}, {counted_records(records, record_type)}", (
        "ok" if records else "empty"
    )


# WDK counts a transcript answer in genes, so its count names genes.
_COUNTED_AS = {"sequence": "protein", "transcript": "gene"}


def counted_noun(record_type: str | None) -> str:
    """The noun the site counts that record type in."""
    if not record_type:
        return "record"
    return _COUNTED_AS.get(record_type, record_type.replace("_", " "))


def counted_records(count: int, record_type: str | None) -> str:
    """The count in the noun the site counts that record type in."""
    return count_noun(count, counted_noun(record_type))


def serialize_step(
    graph: StrategyGraph,
    step: StrategyStep,
    sync_state: SyncStateProtocol | None = None,
) -> StepResponse:
    """Serialize a step for AI tool responses."""
    return step_response(
        step,
        steps=graph.steps,
        record_type=graph.record_type,
        words=graph.words,
        sync=sync_state,
    )


# ---------------------------------------------------------------------------
# Graph snapshot and context plan
# ---------------------------------------------------------------------------


def find_root_step_ids(graph: StrategyGraph) -> list[str]:
    """Return root step IDs in sorted order.

    Uses the incrementally-maintained ``graph.roots`` set (O(1)) instead of
    recomputing from scratch.
    """
    return sorted(graph.roots)


def build_graph_snapshot(
    session: StrategySession, graph: StrategyGraph
) -> GraphSnapshotContent:
    sync_state = session.sync_state
    ctx = build_context_strategy_ast(session, graph)
    roots = find_root_step_ids(graph)

    steps: list[JSONObject] = [
        serialize_step(graph, step, sync_state).model_dump(
            by_alias=True, exclude_none=True, mode="json"
        )
        for step in graph.steps.values()
    ]
    edges: list[GraphEdge] = [
        GraphEdge(source_id=input_id, target_id=step.id, kind=kind)
        for step in graph.steps.values()
        for kind, input_id in [
            ("primary", step.primary_input_id),
            ("secondary", step.secondary_input_id),
        ]
        if input_id is not None
    ]

    return GraphSnapshotContent(
        graph_id=graph.id,
        graph_name=graph.name,
        record_type=ctx.record_type if ctx else None,
        name=ctx.name if ctx else graph.name,
        description=ctx.description if ctx else None,
        root_step_id=roots[0] if len(roots) == 1 else None,
        steps=steps,
        edges=edges,
        strategy_ast=ctx.strategy_ast if ctx else None,
    )


def build_context_strategy_ast(
    session: StrategySession, graph: StrategyGraph
) -> ContextStrategyAstPayload | None:
    root_id = graph.primary_root_id()
    if root_id is None:
        return None
    if graph.get_step(root_id) is None:
        return None
    record_type = graph.record_type
    if not record_type:
        return None
    description = strategy_description(graph, root_id)
    sync_state = session.sync_state
    strategy_ast = graph.to_strategy_ast(root_id, sync_state=sync_state)
    if not strategy_ast:
        return None
    strategy_ast.description = description
    return ContextStrategyAstPayload(
        graph_id=graph.id,
        graph_name=graph.name,
        strategy_ast=strategy_ast,
        record_type=record_type,
        name=graph.name,
        description=description,
    )


# ---------------------------------------------------------------------------
# Response builders (combine step + graph context)
# ---------------------------------------------------------------------------


def step_ok_response(
    session: StrategySession, graph: StrategyGraph, step: StrategyStep
) -> StepOkResponse:
    """Serialize a step as an ``ok=True`` response with a full graph snapshot.

    This combines the three-step pattern used after successful step
    mutations: serialize the step, mark ok, wrap with graph context.
    """
    sync_state = session.sync_state
    ctx = build_context_strategy_ast(session, graph)
    return StepOkResponse(
        step=serialize_step(graph, step, sync_state),
        graph_id=ctx.graph_id if ctx else graph.id,
        graph_name=ctx.graph_name if ctx else graph.name,
        record_type=ctx.record_type if ctx else None,
        name=ctx.name if ctx else graph.name,
        description=ctx.description if ctx else None,
        strategy_ast=ctx.strategy_ast if ctx else None,
        graph_snapshot=build_graph_snapshot(session, graph),
    )


def with_strategy_ast_payload(
    session: StrategySession, graph: StrategyGraph, payload: JSONObject
) -> JSONObject:
    plan_payload = build_context_strategy_ast(session, graph)
    if plan_payload:
        payload.update(plan_payload.model_dump(by_alias=True, exclude_none=True))
    else:
        payload.setdefault("graphId", graph.id)
        payload.setdefault("graphName", graph.name)
    return payload


def with_full_graph(
    session: StrategySession, graph: StrategyGraph, payload: JSONObject
) -> JSONObject:
    response = with_strategy_ast_payload(session, graph, payload)
    response["graphSnapshot"] = build_graph_snapshot(session, graph).model_dump(
        by_alias=True, exclude_none=True, mode="json"
    )
    return response
