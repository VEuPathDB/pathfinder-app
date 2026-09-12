"""Per-step edits of an existing strategy, each applied through the commit path."""

from __future__ import annotations

from typing import cast

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.types import JSONArray, JSONObject
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import ColocationParams, CombineOp, StepKind
from veupathdb.errors import ValidationError
from veupathdb_mcp import ToolErrorPayload, tool_error
from veupathdb_mcp.catalog import (
    ValidationCallbacks,
    make_validation_callbacks,
    validate_parameters,
)

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._graph_helpers import (
    step_ok_response,
    with_full_graph,
)
from pathfinder.ai.tools.standalone._strategy_refusals import (
    _no_graph,
    _refused,
    _step_edit_refused,
    _step_not_found,
    _wdk_refused_the_edit,
)
from pathfinder.ai.tools.standalone._stream_parts import (
    graph_snapshot_chunk,
    strategy_link_chunk,
)
from pathfinder.ai.tools.standalone._validation_helpers import (
    StepOkResponse,
    StepTreePayload,
    get_graph,
    get_graph_and_step,
    validation_error_payload,
    validation_model_retry,
)
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.operations import (
    DeleteResolution,
    DeleteStepOp,
    GraphOperation,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import value_contradiction
from pathfinder.domain.strategy.stated_shape import (
    StatedShape,
    shape_after,
)
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.strategies.commit import CommitResult, apply_and_commit
from pathfinder.services.strategies.insert_saved import (
    insert_saved_into_conversation,
)


def _make_callbacks(site_id: str) -> ValidationCallbacks:
    return make_validation_callbacks(site_id, error_payload=validation_error_payload)


async def _commit_or_retry(deps: AgentDeps, op: GraphOperation) -> CommitResult:
    """Apply one operation, or answer with why the strategy refused it."""
    try:
        return await apply_and_commit(deps=deps.to_strategy_context(), op=op)
    except ApplyError as exc:
        msg = f"REJECTED: {exc}. Nothing was applied and the strategy is unchanged."
        raise ModelRetry(msg) from exc


async def update_leaf_params(
    ctx: RunContext[AgentDeps],
    step_id: str,
    parameters: dict[str, ParamValue],
    *,
    graph_id: str | None = None,
) -> ToolReturn[StepOkResponse | ToolErrorPayload]:
    """Update a leaf step's parameters - a partial patch.

    Only the params you pass are changed; the step's other params are kept, so
    you can update one param without re-supplying the whole search config. Each
    value MUST be wrapped in its typed shape - see the ``valueFormat`` field
    from ``get_search_overview`` for the exact template per param. Example:
    ``{"organism": {"type": "multi-pick-vocabulary", "values": ["Pf3D7"]}}``.
    """
    deps = ctx.deps
    session = deps.strategy_session
    resolved = get_graph_and_step(session, graph_id, step_id)
    if isinstance(resolved, ToolErrorPayload):
        return _step_not_found(ctx, resolved, step_id)
    graph, step = resolved

    if step.kind is not StepKind.SEARCH:
        msg = (
            f"VALIDATION_ERROR: update_leaf_params only applies to leaf "
            f"steps; step {step_id!r} is a "
            f"{step.kind.value}. Use update_combine_operator (combine) "
            f"or replace_subtree to change a non-leaf step."
        )
        raise ModelRetry(msg)

    contradiction = value_contradiction(
        deps.agent_state.operational_spec_draft,
        step_id=step_id,
        parameters=parameters,
    )
    if contradiction is not None:
        raise ModelRetry(contradiction)

    record_type = graph.record_type or "transcript"
    merged = {**step.parameters, **parameters}
    try:
        canonical = await validate_parameters(
            SearchContext(deps.site_id, record_type, step.search_name or ""),
            parameters=merged,
            callbacks=_make_callbacks(deps.site_id),
        )
    except ValidationError as exc:
        raise validation_model_retry(
            exc,
            recordType=record_type,
            searchName=step.search_name,
        ) from exc

    result = await _commit_or_retry(
        deps, UpdateStepParamsOp(step_id=step_id, parameters=dict(canonical.params))
    )
    refusal = _wdk_refused_the_edit(result)
    if refusal is not None:
        return _step_edit_refused(ctx, refusal, step_id)
    return with_summary(
        step_ok_response(session, graph, step),
        f"{step_id}: {count_noun(len(parameters), 'parameter')} updated",
        ctx=ctx,
        extra=[graph_snapshot_chunk(session, graph)],
    )


async def update_combine_operator(
    ctx: RunContext[AgentDeps],
    step_id: str,
    operator: CombineOp,
    colocation_params: ColocationParams | None = None,
    *,
    graph_id: str | None = None,
) -> ToolReturn[StepOkResponse | ToolErrorPayload]:
    """Update a combine step's operator (and colocation params if COLOCATE)."""
    deps = ctx.deps
    session = deps.strategy_session
    resolved = get_graph_and_step(session, graph_id, step_id)
    if isinstance(resolved, ToolErrorPayload):
        return _step_not_found(ctx, resolved, step_id)
    graph, step = resolved

    if step.kind is not StepKind.COMBINE:
        msg = (
            f"VALIDATION_ERROR: update_combine_operator only applies to "
            f"combine steps; step {step_id!r} is a {step.kind.value}."
        )
        raise ModelRetry(msg)

    if operator == CombineOp.COLOCATE and colocation_params is None:
        msg = "VALIDATION_ERROR: COLOCATE operator requires colocation_params."
        raise ModelRetry(msg)
    if operator != CombineOp.COLOCATE and colocation_params is not None:
        msg = "VALIDATION_ERROR: colocation_params is only valid for COLOCATE."
        raise ModelRetry(msg)
    result = await _commit_or_retry(
        deps,
        UpdateCombineOperatorOp(
            step_id=step_id,
            operator=operator,
            colocation_params=colocation_params,
        ),
    )
    refusal = _wdk_refused_the_edit(result)
    if refusal is not None:
        return _step_edit_refused(ctx, refusal, step_id)
    return with_summary(
        step_ok_response(session, graph, step),
        f"{step_id} now {operator.value}",
        ctx=ctx,
        extra=[graph_snapshot_chunk(session, graph)],
    )


async def update_step_metadata(
    ctx: RunContext[AgentDeps],
    step_id: str,
    display_name: str,
    *,
    graph_id: str | None = None,
) -> ToolReturn[StepOkResponse | ToolErrorPayload]:
    """Update a step's display name. Local-only - no WDK call."""
    deps = ctx.deps
    session = deps.strategy_session
    resolved = get_graph_and_step(session, graph_id, step_id)
    if isinstance(resolved, ToolErrorPayload):
        return _step_not_found(ctx, resolved, step_id)
    graph, step = resolved

    result = await _commit_or_retry(
        deps, UpdateStepMetaOp(step_id=step_id, display_name=display_name)
    )
    refusal = _wdk_refused_the_edit(result)
    if refusal is not None:
        return _step_edit_refused(ctx, refusal, step_id)
    return with_summary(
        step_ok_response(session, graph, step),
        f"{step_id} renamed to {display_name}",
        ctx=ctx,
        extra=[graph_snapshot_chunk(session, graph)],
    )


async def delete_step(
    ctx: RunContext[AgentDeps],
    step_id: str,
    *,
    resolution: DeleteResolution = DeleteResolution.COLLAPSE_COMBINE,
    graph_id: str | None = None,
) -> ToolReturn[JSONObject]:
    """Delete a step and re-wire the tree to preserve a single root.

    ``resolution`` selects the disambiguation policy. Defaults to
    ``collapse-combine`` which drops the step + its parent combine and
    reconnects the sibling to the grandparent.
    """
    deps = ctx.deps
    session = deps.strategy_session
    graph = get_graph(session, graph_id)
    if graph is None:
        return _no_graph(ctx, graph_id)
    if step_id not in graph.steps:
        msg = (
            f"VALIDATION_ERROR: Step {step_id!r} not found. Valid step "
            f"ids: {sorted(graph.steps.keys())}."
        )
        raise ModelRetry(msg)

    result = await _commit_or_retry(
        deps, DeleteStepOp(step_id=step_id, resolution=resolution)
    )
    # The graph keeps the delete whatever WDK answers, so the spec drops the
    # criteria of the removed steps before the answer is decided.
    deps.agent_state.drop_criteria_for_steps(result.dropped_step_ids)
    refusal = _wdk_refused_the_edit(result)
    if refusal is not None:
        return _refused(ctx, refusal, f"VEuPathDB refused the delete of {step_id}")
    response: JSONObject = {
        "ok": True,
        "deleted": cast("JSONArray", result.dropped_step_ids),
        "graphId": graph.id,
    }
    return with_summary(
        with_full_graph(session, graph, response),
        f"Deleted {step_id}, {len(graph.steps)} steps left",
        ctx=ctx,
        extra=[graph_snapshot_chunk(session, graph)],
    )


def _refuse_a_write_the_spec_did_not_state(
    deps: AgentDeps, graph: StrategyGraph, op: ReplaceSubtreeOp
) -> None:
    """The write leaves the strategy holding the criteria the spec states.

    The spec addresses this graph by step id, so a criterion that answers to no
    step of it, before or after the write, states nothing about it.
    """
    spec = deps.agent_state.operational_spec_draft
    shape = shape_after(op, graph=graph, criteria=[c.id for c in spec.criteria])
    if not shape.stated or shape.holds:
        return
    criteria = {c.id: c for c in spec.criteria if c.id in shape.stated}
    raise ModelRetry(_write_refusal(shape, criteria))


def _write_refusal(shape: StatedShape, criteria: dict[str, Criterion]) -> str:
    parts = ["VALIDATION_ERROR: nothing was applied and the strategy is unchanged."]
    if shape.lost:
        named = ", ".join(f"{cid} ({criteria[cid].text})" for cid in shape.lost)
        parts.append(
            f"This subtree would drop {len(shape.lost)} of the criteria the "
            f"strategy states: {named}."
        )
    if shape.unstated:
        parts.append(f"It would add {list(shape.unstated)}, which no criterion states.")
    if shape.adopted:
        parts.append(f"It would adopt {list(shape.adopted)} from outside the strategy.")
    if shape.stranded:
        parts.append(f"It would strand {list(shape.stranded)}.")
    parts.append(
        "Send a subtree that keeps every step id the spec names, or change the "
        "criteria first."
    )
    return " ".join(parts)


async def replace_subtree(
    ctx: RunContext[AgentDeps],
    step_id: str,
    new_subtree: StepTreePayload,
    *,
    graph_id: str | None = None,
) -> ToolReturn[JSONObject]:
    """Replace the subtree rooted at ``step_id`` with a new tree."""
    deps = ctx.deps
    session = deps.strategy_session
    graph = get_graph(session, graph_id)
    if graph is None:
        return _no_graph(ctx, graph_id)
    if step_id not in graph.steps:
        msg = (
            f"VALIDATION_ERROR: Step {step_id!r} not found. Valid step "
            f"ids: {sorted(graph.steps.keys())}."
        )
        raise ModelRetry(msg)

    op = ReplaceSubtreeOp(step_id=step_id, subtree=new_subtree)
    _refuse_a_write_the_spec_did_not_state(deps, graph, op)
    result = await _commit_or_retry(deps, op)
    refusal = _wdk_refused_the_edit(result)
    if refusal is not None:
        return _refused(ctx, refusal, f"VEuPathDB refused the subtree at {step_id}")
    payload: JSONObject = {
        "ok": True,
        "replacedStepId": step_id,
        "droppedStepIds": cast("JSONArray", result.dropped_step_ids),
        "graphId": graph.id,
    }
    metadata = [graph_snapshot_chunk(session, graph)]
    sync_result = result.sync_result
    if sync_result is not None and sync_result.wdk_url is not None:
        metadata.append(
            strategy_link_chunk(
                strategy_id=graph.id,
                url=sync_result.wdk_url,
                title=graph.name,
            ),
        )
    return with_summary(
        with_full_graph(session, graph, payload),
        f"Replaced {step_id}, {len(graph.steps)} steps",
        ctx=ctx,
        extra=metadata,
    )


async def insert_saved_strategy(
    ctx: RunContext[AgentDeps],
    target_step_id: str,
    saved_wdk_strategy_id: int,
    *,
    operator: CombineOp = CombineOp.INTERSECT,
    graph_id: str | None = None,
) -> ToolReturn[JSONObject]:
    """Insert a saved WDK strategy as a new combine input next to ``target_step_id``."""
    deps = ctx.deps
    session = deps.strategy_session
    graph = get_graph(session, graph_id)
    if graph is None:
        return _no_graph(ctx, graph_id)
    if target_step_id not in graph.steps:
        msg = (
            f"VALIDATION_ERROR: Step {target_step_id!r} not found. Valid "
            f"step ids: {sorted(graph.steps.keys())}."
        )
        raise ModelRetry(msg)

    if deps.conversation_id is None or deps.db_session_factory is None:
        return with_summary(
            cast(
                "JSONObject",
                tool_error(
                    ErrorCode.INTERNAL_ERROR,
                    "insert_saved_strategy requires a persistent conversation context",
                ).model_dump(by_alias=True, mode="json"),
            ),
            "This thread cannot insert a saved strategy",
            ctx=ctx,
            status="warn",
        )

    result = await insert_saved_into_conversation(
        deps=deps.to_strategy_context(),
        target_step_id=target_step_id,
        saved_wdk_strategy_id=saved_wdk_strategy_id,
        operator=operator,
    )

    payload: JSONObject = {
        "ok": True,
        "insertedSavedStrategyId": result.inserted_saved_wdk_strategy_id,
        "insertedSavedStrategyName": result.inserted_saved_name,
        "combineStepId": result.combine_step_id,
        "wdkStrategyId": result.wdk_strategy_id,
        "graphId": graph.id,
    }
    return with_summary(
        with_full_graph(session, graph, payload),
        f"Inserted {result.inserted_saved_name} at {target_step_id}",
        ctx=ctx,
        extra=[graph_snapshot_chunk(session, graph)],
    )
