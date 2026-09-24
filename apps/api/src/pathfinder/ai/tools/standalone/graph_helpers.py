"""Graph snapshot building, step serialization, and strategy naming.

Functions that operate on ``StrategyGraph`` to produce serialized
responses and context payloads for AI tool results.
"""

from assistant_core.graph.stream_events import ToolSummaryStatus
from assistant_core.graph.tool_summary import count_noun
from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy import StepValidation, StrategyStep

from pathfinder.ai.tools.standalone._validation_helpers import (
    ContextStrategyAstPayload,
    GraphEdge,
    GraphSnapshotContent,
    StepOkResponse,
)
from pathfinder.domain.strategy.build_outcome import citable_count
from pathfinder.domain.strategy.combine_naming import combine_name
from pathfinder.domain.strategy.explain import explain_operation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_status import step_status
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.services.strategies.schemas import StepResponse, step_rationale_of

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


def derive_strategy_description(
    record_type: str | None,
    root_step: StrategyStep,
) -> str:
    kind = root_step.kind.value
    if kind == "search":
        summary = root_step.display_name or root_step.search_name
        verb = "Find"
    elif kind == "transform":
        summary = root_step.display_name or root_step.search_name
        verb = "Transform"
    else:
        if root_step.operator is not None:
            summary = explain_operation(root_step.operator)
        else:
            summary = root_step.display_name or "combine"
        verb = "Combine"
    summary = (summary or "").strip()
    if not summary:
        summary = "results"
    if record_type:
        return f"{verb} {record_type} results for {summary}."
    return f"{verb} results for {summary}."


# ---------------------------------------------------------------------------
# Step serialization
# ---------------------------------------------------------------------------


def build_step_response(
    graph: StrategyGraph | None,
    step: StrategyStep,
    sync_state: SyncStateProtocol | None = None,
) -> StepResponse:
    """Build a StepResponse from a StrategyStepNode + graph/sync enrichment."""
    wdk_step_id: int | None = None
    validation: StepValidation | None = None
    estimated_size: int | None = None
    record_type: str | None = None
    wdk_push_error: str | None = None

    if graph:
        record_type = graph.record_type
    if sync_state:
        wdk_step_id = sync_state.wdk_step_ids.get(step.id)
        validation = sync_state.step_validations.get(step.id)
        wdk_push_error = sync_state.wdk_push_errors.get(step.id)
        estimated_size = citable_count(
            step.id,
            counts=sync_state.step_counts,
            refused=sync_state.wdk_push_errors,
        )

    return StepResponse(
        id=step.id,
        kind=step.kind.value,
        display_name=(
            combine_name(step.display_name, step.search_name, step.operator)
            or step.display_label
        ),
        criterion_text=graph.words.criterion_texts.get(step.id) if graph else None,
        rationale=step_rationale_of(graph.words, step) if graph else None,
        search_name=step.search_name,
        record_type=record_type,
        parameters=step.parameters or None,
        operator=step.operator.value if step.operator else None,
        colocation_params=step.colocation_params,
        primary_input_step_id=step.primary_input_id,
        secondary_input_step_id=step.secondary_input_id,
        estimated_size=estimated_size,
        wdk_step_id=wdk_step_id,
        status=step_status(
            step,
            wdk_step_id=wdk_step_id,
            validation=validation,
            has_open_params=False,
        ),
        is_filtered=bool(step.filters),
        wdk_push_error=wdk_push_error,
        validation=validation,
        filters=step.filters or None,
        analyses=step.analyses or None,
        reports=step.reports or None,
    )


def count_summary(
    step_count: int, records: int | None, record_type: str | None
) -> tuple[str, ToolSummaryStatus]:
    """The one line every strategy surface reports its size with.

    A count nobody measured is reported as missing, never spent as a zero.
    """
    if records is None:
        return f"{step_count} steps, count not available", "warn"
    counted = count_noun(records, record_type or "record")
    return f"{step_count} steps, {counted}", "ok" if records else "empty"


def serialize_step(
    graph: StrategyGraph,
    step: StrategyStep,
    sync_state: SyncStateProtocol | None = None,
) -> StepResponse:
    """Serialize a step for AI tool responses."""
    return build_step_response(graph, step, sync_state)


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
        build_step_response(graph, step, sync_state).model_dump(
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
    root_step = graph.get_step(root_id)
    if not root_step:
        return None
    record_type = graph.record_type
    if not record_type:
        return None
    description = graph.description
    if not description:
        description = derive_strategy_description(record_type, root_step)
    graph.description = description
    sync_state = session.sync_state
    strategy_ast = graph.to_strategy_ast(root_id, sync_state=sync_state)
    if not strategy_ast:
        return None
    if description:
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
