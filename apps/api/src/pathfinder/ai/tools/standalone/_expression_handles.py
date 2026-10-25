from __future__ import annotations

from dataclasses import replace

from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.domain.strategy.computed_groups import is_comparison_handle
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    UnknownExpressionError,
    expression_handle,
    held_expressions,
    resolved_params,
)


def held_handle(
    state: AgentToolState, expression: str, pattern: PhyleticPattern, reading: str
) -> str:
    handle = expression_handle(expression)
    state.built_expressions[handle] = BuiltPattern(
        expression=expression, pattern=pattern, reading=reading
    )
    return handle


def with_stored_expressions(
    state: AgentToolState, call: CriterionCall
) -> CriterionCall:
    match call.params.get(PHYLETIC_EXPRESSION_PARAM):
        case str() as text if is_comparison_handle(text):
            msg = (
                f"{PHYLETIC_EXPRESSION_PARAM} names {text.strip()}, the handle of a "
                "computed comparison, which no expression states. Pass it to "
                "set_criterion as computed_groups instead; nothing was recorded."
            )
            raise ModelRetry(msg)
        case str() as text:
            proposed = {PHYLETIC_EXPRESSION_PARAM: text}
        case _:
            return call
    held = held_expressions(state.built_expressions, state.operational_spec_draft)
    try:
        resolved = resolved_params(proposed, held)
    except UnknownExpressionError as exc:
        msg = (
            f"{PHYLETIC_EXPRESSION_PARAM} names {exc.handle}, and no expression of "
            "this conversation is held under that handle: neither "
            "build_phyletic_expression nor a bound criterion wrote it. Call "
            "build_phyletic_expression and bind the handle it returns; nothing was "
            "recorded."
        )
        raise ModelRetry(msg) from exc
    return replace(call, params={**call.params, **resolved})


__all__ = ["held_handle", "with_stored_expressions"]
