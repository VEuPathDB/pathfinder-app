from __future__ import annotations

from dataclasses import replace

from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM
from veupathdb_mcp.catalog import PhyleticPattern

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.domain.refusal import Problems, RefusalKey
from strategist.domain.strategy.computed_groups import is_comparison_handle
from strategist.domain.strategy.expression_handles import (
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


_EXPRESSION = RefusalKey(check="expression", parameter=PHYLETIC_EXPRESSION_PARAM)


def with_stored_expressions(
    state: AgentToolState, call: CriterionCall
) -> tuple[CriterionCall, Problems]:
    """The call with each expression handle it names read back, or the call as
    sent and the problem a handle no expression stands for makes."""
    match call.params.get(PHYLETIC_EXPRESSION_PARAM):
        case str() as text if is_comparison_handle(text):
            return call, Problems.one(
                _EXPRESSION,
                f"{PHYLETIC_EXPRESSION_PARAM} names {text.strip()}, the handle of a "
                "computed comparison, which no expression states. Pass it to "
                "set_criterion as computed_groups instead.",
            )
        case str() as text:
            proposed = {PHYLETIC_EXPRESSION_PARAM: text}
        case _:
            return call, Problems()
    held = held_expressions(state.built_expressions, state.operational_spec_draft)
    try:
        resolved = resolved_params(proposed, held)
    except UnknownExpressionError as exc:
        return call, Problems.one(
            _EXPRESSION,
            f"{PHYLETIC_EXPRESSION_PARAM} names {exc.handle}, and no expression of "
            "this conversation is held under that handle: neither "
            "build_phyletic_expression nor a bound criterion wrote it. Call "
            "build_phyletic_expression and bind the handle it returns.",
        )
    return replace(call, params={**call.params, **resolved}), Problems()


__all__ = ["held_handle", "with_stored_expressions"]
