"""Declarative strategy tools for the execution agent.

A build takes one complete step tree. Every later edit builds a graph
operation and applies it through the single commit path.
"""

from __future__ import annotations

from typing import cast

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONArray, JSONObject
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import ValidationError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._validation_helpers import (
    OperationPayload,
    StepTreePayload,
    get_graph,
    validation_model_retry,
)
from pathfinder.ai.tools.standalone.graph_helpers import count_summary
from pathfinder.ai.tools.standalone.strategy_refusals import (
    _no_graph,
    _refused,
    wdk_refused_the_edit,
)
from pathfinder.ai.tools.standalone.stream_parts import (
    graph_snapshot_chunk,
    strategy_link_chunk,
)
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies.commit import apply_operations_and_commit
from pathfinder.services.strategies.spec_build import build_strategy_from_spec

logger = get_logger(__name__)


def _build_outcome_payload(outcome: BuildOutcome, graph: StrategyGraph) -> JSONObject:
    """Serializes a build outcome into the tool response payload."""
    payload: JSONObject = {
        "ok": outcome.fully_succeeded,
        "wdkStrategyId": outcome.wdk_strategy_id,
        "wdkUrl": outcome.wdk_url,
        "rootCount": outcome.root_count,
        "stepCount": len(graph.steps),
        "pushedStepIds": cast("JSONArray", outcome.pushed_step_ids),
        "failedSteps": cast(
            "JSONArray",
            [
                {
                    "stepId": f.step_id,
                    "searchName": f.search_name,
                    "error": f.error,
                }
                for f in outcome.failed_steps
            ],
        ),
        "skippedStepIds": cast("JSONArray", outcome.skipped_step_ids),
        "zeroStepIds": cast("JSONArray", outcome.zero_step_ids),
        "counts": cast("JSONObject", dict(outcome.counts)),
    }
    if outcome.failed_steps:
        payload["hint"] = (
            "Some steps failed to push to WDK. Local AST is intact - use "
            "update_leaf_params to fix the failed step's parameters, or "
            "delete_step / replace_subtree to restructure. The build will "
            "retry on next mutation."
        )
    return payload


async def build_strategy(
    ctx: RunContext[AgentDeps],
    root: StepTreePayload,
    *,
    name: str | None = None,
    description: str | None = None,
    graph_id: str | None = None,
    base_revision: str | None = None,
) -> ToolReturn[JSONObject]:
    """Materialize a complete strategy from a single declarative tree.

    Use this to build a strategy from nothing. To CHANGE a strategy that
    already exists, use `apply_operations` instead -- this replaces the whole
    graph, so it costs the entire strategy in tokens and overwrites anything
    the researcher edited in the meantime.

    Replacing a non-empty strategy requires `base_revision` (the `revision`
    from `get_strategy`), so a replacement is always something you chose
    rather than something that happened.

    The ENTIRE strategy is passed as a single `root` argument - a recursive
    StrategyStepNode where every combine has its inputs nested inside it.
    Do NOT put `primaryInput`, `secondaryInput`, `searchName`, or
    `parameters` at the top level of the tool args - they ONLY exist
    inside `root` (and inside nodes within `root`).

    Example - INTERSECT(UNION(A, B), C) where A, B, C are leaf searches::

        build_strategy(
            root={
                "operator": "INTERSECT",
                "primaryInput": {
                    "operator": "UNION",
                    "primaryInput":   {"searchName": "A", "parameters": {...}},
                    "secondaryInput": {"searchName": "B", "parameters": {...}},
                },
                "secondaryInput": {"searchName": "C", "parameters": {...}},
            },
            name="...",
        )

    To add a NEW set as a sibling of an existing tree, wrap the existing
    tree in a new combine: the existing tree becomes `primaryInput`, the
    new set becomes `secondaryInput`, and the new combine replaces `root`.
    """
    deps = ctx.deps
    session = deps.strategy_session
    graph = get_graph(session, graph_id)
    if graph is None:
        return _no_graph(ctx, graph_id)

    current = _current_revision(graph)
    if current and base_revision != current:
        msg = (
            f"CONFLICT: this strategy already has {len(graph.steps)} step(s), and "
            f"build_strategy replaces all of them. If you meant to change it, "
            f"call apply_operations with base_revision={current!r} and send only "
            f"the edits. If you really do mean to replace the whole strategy, "
            f"re-call build_strategy with base_revision={current!r}."
        )
        raise ModelRetry(msg)

    try:
        outcome = await build_strategy_from_spec(
            deps=deps.to_strategy_context(),
            root=root,
            name=name,
            description=description,
        )
    except ApplyError as exc:
        msg = f"REJECTED: {exc}. Nothing was built and the strategy is unchanged."
        raise ModelRetry(msg) from exc
    payload = _build_outcome_payload(outcome, graph)
    metadata = [graph_snapshot_chunk(session, graph)]
    if outcome.wdk_url is not None:
        metadata.append(
            strategy_link_chunk(
                strategy_id=graph.id,
                url=outcome.wdk_url,
                title=graph.name,
            ),
        )
    summary, status = count_summary(len(graph.steps), outcome.root_count)
    return with_summary(payload, summary, ctx=ctx, status=status, extra=metadata)


def _current_revision(graph: StrategyGraph) -> str:
    return strategy_revision(graph.to_strategy_ast())


async def apply_operations(
    ctx: RunContext[AgentDeps],
    base_revision: str,
    operations: list[OperationPayload],
    graph_id: str | None = None,
) -> ToolReturn[JSONObject]:
    """Edit the strategy with a batch of operations, not a whole new tree.

    Prefer this over `build_strategy` for any change to a strategy that
    already exists: it sends only what changes, so adding one step does not
    mean restating every existing step's parameters.

    `base_revision` is the `revision` from the most recent `get_strategy`.
    If the strategy changed since then -- typically because the researcher
    edited a parameter in the UI -- nothing is applied and you are told the
    current revision, so you can re-read and decide whether your edit still
    makes sense. Use `""` for a strategy that does not exist yet.

    Operations apply in order and all land together; if one is rejected the
    strategy is left exactly as it was.

    A batch never removes a step. Two tools here do, and each asks the
    researcher first: ``delete_step`` for one step, which chooses how the tree
    is re-wired and takes the removed steps out of the spec's criteria, and
    ``replace_subtree`` for one branch. A batch that overwrites an input slot
    is refused for the same reason, so remove the step that slot holds with
    ``delete_step`` first, or wire it back in under the step that replaces it.
    """
    deps = ctx.deps
    session = deps.strategy_session
    graph = get_graph(session, graph_id)
    if graph is None:
        return _no_graph(ctx, graph_id)

    if not operations:
        msg = (
            "VALIDATION_ERROR: apply_operations needs at least one operation. "
            "Pass the edits you want to make, or call get_strategy to look first."
        )
        raise ModelRetry(msg)

    current = _current_revision(graph)
    if base_revision != current:
        msg = (
            f"CONFLICT: the strategy changed since you last read it "
            f"(you passed base_revision={base_revision!r}, current is "
            f"{current!r}). Nothing was applied. Call get_strategy to see the "
            f"current state, then re-issue only the edits that still apply -- "
            f"the researcher may have already made this change themselves."
        )
        raise ModelRetry(msg)

    try:
        result = await apply_operations_and_commit(
            deps=deps.to_strategy_context(),
            ops=operations,
        )
    except ApplyError as exc:
        # A rejected batch rolls back, so the base revision stays valid.
        msg = (
            f"REJECTED: {exc}. Nothing was applied and the strategy is "
            f"unchanged, so base_revision={current!r} is still valid. Fix the "
            f"offending operation and send the batch again."
        )
        raise ModelRetry(msg) from exc
    except ValidationError as exc:
        raise validation_model_retry(
            exc, recordType=graph.record_type or "transcript"
        ) from exc
    refusal = wdk_refused_the_edit(result)
    if refusal is not None:
        return _refused(ctx, refusal, "VEuPathDB refused this batch")
    payload: JSONObject = {
        "applied": len(operations),
        "description": result.description,
        "droppedStepIds": cast("JSONArray", list(result.dropped_step_ids)),
        "revision": _current_revision(graph),
    }
    return with_summary(
        payload,
        f"{len(operations)} operations applied, {len(graph.steps)} steps",
        ctx=ctx,
        extra=[graph_snapshot_chunk(session, graph)],
    )
