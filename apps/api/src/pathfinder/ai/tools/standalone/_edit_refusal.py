from __future__ import annotations

from collections.abc import Sequence

from pydantic import JsonValue

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._step_read import own_class
from pathfinder.domain.strategy.operations import GraphOperation, UpdateStepParamsOp


async def refusal_context(deps: AgentDeps, op: GraphOperation) -> dict[str, JsonValue]:
    """What a refused value is reported with: the record type and the search of
    the step the operation patches."""
    session = deps.strategy_session
    graph = session.get_graph(None)
    match op:
        case UpdateStepParamsOp() if graph is not None:
            step = graph.get_step(op.step_id)
            if step is not None and step.search_name:
                return {
                    "recordType": await own_class(session, step),
                    "searchName": step.search_name,
                }
        case _:
            pass
    return {}


async def batch_refusal_context(
    deps: AgentDeps, ops: Sequence[GraphOperation]
) -> dict[str, JsonValue]:
    edited: list[UpdateStepParamsOp] = []
    for op in ops:
        match op:
            case UpdateStepParamsOp():
                edited.append(op)
            case _:
                pass
    if len({op.step_id for op in edited}) != 1:
        return {}
    return await refusal_context(deps, edited[0])
