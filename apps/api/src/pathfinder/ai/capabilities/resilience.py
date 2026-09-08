"""The ToolResilience capability, which routes tool failures to a recovery strategy."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any

from assistant_core.platform.logging import get_logger
from langgraph.errors import GraphInterrupt
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import RunContext, ToolDefinition
from veupathdb.errors import WDKError

from pathfinder.ai.capabilities.error_classification import (
    ErrorCategory,
    build_error_directive,
    classify_error,
)
from pathfinder.ai.graph.runtime import OUTAGE_GIVE_UP_THRESHOLD, AgentDeps

_WDK_STATUS_NOT_FOUND = 404
_WDK_STATUS_UNPROCESSABLE = 422

logger = get_logger(__name__)

DEFAULT_CIRCUIT_BREAK_THRESHOLD: int = 3

_STEP_TREE_FIELDS = frozenset(
    {
        "primaryInput",
        "secondaryInput",
        "primary_input",
        "secondary_input",
        "searchName",
        "search_name",
        "parameters",
        "operator",
        "displayName",
        "display_name",
    },
)

_BUILD_STRATEGY_TOPLEVEL_ALLOWED = frozenset(
    {"root", "name", "description", "graph_id", "graphId"},
)


def _shape_error_hint(
    tool_name: str,
    args: object,
    error: PydanticValidationError,
) -> str | None:
    if not isinstance(args, dict):
        return None
    param_hint = _param_value_shape_hint(args, error)
    if param_hint is not None:
        return param_hint
    if len(args) == 1:
        return _wrapped_args_hint(tool_name, args, error)
    if tool_name == "build_strategy":
        return _build_strategy_misplaced_hint(args, error)
    return None


_PARAM_VALUE_FIELDS = frozenset(
    {
        "context_values",
        "parameters",
        "target_parameters",
        "fixed_parameters",
        "controls_extra_parameters",
    }
)

_PARAM_VALUE_SHAPE_ERROR_TYPES = frozenset(
    {
        "union_tag_not_found",
        "union_tag_invalid",
        "model_attributes_type",
        "dict_type",
    }
)


def _param_value_shape_hint(
    args: dict[str, object],
    error: PydanticValidationError,
) -> str | None:
    bad: list[tuple[str, object]] = []
    for entry in error.errors():
        if entry.get("type") not in _PARAM_VALUE_SHAPE_ERROR_TYPES:
            continue
        loc = entry.get("loc") or ()
        if not loc or loc[0] not in _PARAM_VALUE_FIELDS:
            continue
        param_name = loc[1] if len(loc) > 1 and isinstance(loc[1], str) else "<unknown>"
        bad.append((param_name, entry.get("input")))
    if not bad:
        return None
    listing = ", ".join(f"{name!r}={input_!r}" for name, input_ in bad)
    return (
        f"Parameter value(s) {listing} were passed as raw scalars/lists. "
        "Every parameter value MUST be wrapped as a typed object with a `type` "
        "discriminator. Common shapes:\n"
        '  {"type": "string", "value": "..."}\n'
        '  {"type": "single-pick-vocabulary", "value": "<from allowed_values>"}\n'
        '  {"type": "multi-pick-vocabulary", "values": ["<from allowed_values>", ...]}\n'
        '  {"type": "number", "value": <number>}\n'
        "The exact wrapper per param is in the `valueFormat` field of "
        "`get_search_overview` / `get_parameter_options`. Copy that format "
        "verbatim, substitute your chosen value, and re-call."
    )


def _build_strategy_misplaced_hint(
    args: object,
    error: PydanticValidationError,
) -> str | None:
    if not isinstance(args, dict):
        return None
    misplaced = [
        key
        for key in args
        if key in _STEP_TREE_FIELDS and key not in _BUILD_STRATEGY_TOPLEVEL_ALLOWED
    ]
    if not misplaced:
        return None
    del error
    return (
        f"build_strategy received {misplaced!r} at the top level of the "
        "tool arguments. These fields belong INSIDE `root`, not next to "
        "it. The whole strategy tree — including every combine and every "
        "leaf — must be nested under a single `root`. To add a new set "
        "as a sibling of the existing tree, wrap the existing tree in a "
        "new combine: existing tree becomes `primaryInput`, new set "
        "becomes `secondaryInput`, the new combine replaces `root`. "
        "See the build_strategy docstring for a worked example."
    )


def _wrapped_args_hint(
    tool_name: str,
    args: object,
    error: PydanticValidationError,
) -> str | None:
    if not isinstance(args, dict) or len(args) != 1:
        return None
    wrapper_key, wrapper_val = next(iter(args.items()))
    if not isinstance(wrapper_val, dict):
        return None
    missing_top_level: set[str] = set()
    for entry in error.errors():
        if entry.get("type") != "missing":
            continue
        loc = entry.get("loc") or ()
        if len(loc) == 1 and isinstance(loc[0], str):
            missing_top_level.add(loc[0])
    if not missing_top_level:
        return None
    if not missing_top_level.issubset(set(wrapper_val.keys())):
        return None
    return (
        f"{tool_name} received its arguments nested under a single wrapper "
        f"key {wrapper_key!r}. The arguments must be at the TOP LEVEL of "
        f"the tool call, not inside another object. Move the contents of "
        f"{wrapper_key!r} up one level. Specifically, "
        f"{sorted(missing_top_level)!r} must be top-level fields of the "
        f"tool call, not nested under {wrapper_key!r}."
    )


# ---------------------------------------------------------------------------
# Next-action libraries
# ---------------------------------------------------------------------------

_NEXT_ACTIONS_WDK_404_SEARCH = [
    'Call search_for_searches(query="<describe what you need>") to find the correct search name',
    'Call list_searches(record_type="transcript") to see all available searches',
]

_NEXT_ACTIONS_WDK_422 = [
    "Call get_parameter_options for the rejected parameter to see valid values",
    "Use the exact value from the vocabulary, not free text",
]

_NEXT_ACTIONS_SEMANTIC_GENERIC = [
    "Check tool arguments and retry with corrected values",
]

_NEXT_ACTIONS_PERMANENT = [
    "Use alternative tools to accomplish the goal",
    "Ask the user if they can provide the information you were searching for",
]

_NEXT_ACTIONS_UNKNOWN = [
    "Try a different approach using other available tools",
    "If the task requires this tool, inform the user about the limitation",
]


# ---------------------------------------------------------------------------
# Semantic directive builders
# ---------------------------------------------------------------------------


def _semantic_directive(
    error: Exception,
    tool_name: str,
    args: dict[str, Any],
    search_lookup_tools: frozenset[str],
) -> str:
    """Return a context-specific directive for SEMANTIC errors."""
    if isinstance(error, WDKError):
        if error.status == _WDK_STATUS_NOT_FOUND and tool_name in search_lookup_tools:
            return build_error_directive(
                error_type="SEARCH_NOT_FOUND",
                tool_name=tool_name,
                tool_args=args,
                detail=str(error),
                next_actions=_NEXT_ACTIONS_WDK_404_SEARCH,
                do_not="Do not retry with the same search name — it does not exist on this site",
            )
        if error.status == _WDK_STATUS_UNPROCESSABLE:
            return build_error_directive(
                error_type="INVALID_PARAMETER_VALUE",
                tool_name=tool_name,
                tool_args=args,
                detail=str(error),
                next_actions=_NEXT_ACTIONS_WDK_422,
                do_not="Do not pass free-text values for vocabulary parameters",
            )

    return build_error_directive(
        error_type="SEMANTIC_TOOL_ERROR",
        tool_name=tool_name,
        tool_args=args,
        detail=str(error),
        next_actions=_NEXT_ACTIONS_SEMANTIC_GENERIC,
        do_not="Do not retry with the same arguments without correcting them first",
    )


_NEXT_ACTIONS_OUTAGE = [
    "Prefer a DIFFERENT search that covers the same intent for now",
    (
        "If no equivalent search fits, tell the user this search is temporarily "
        "unavailable and they can retry shortly; do not drop it as invalid"
    ),
]


class _TransientArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    search_name: str | None = None


def _outage_directive(tool_name: str, search_name: str, error: Exception) -> str:
    return build_error_directive(
        error_type="SEARCH_UNAVAILABLE",
        tool_name=tool_name,
        tool_args={"search_name": search_name},
        detail=(
            f"'{search_name}' returned repeated transient server errors and did "
            f"not recover within this turn's retries: {error}. The search itself "
            f"is valid; this is a temporary VEuPathDB outage, not a bad call."
        ),
        next_actions=_NEXT_ACTIONS_OUTAGE,
        do_not=(
            f"Do not keep retrying '{search_name}' this turn; the outage is not "
            f"clearing right now. But do NOT treat it as permanently broken or "
            f"drop it as invalid; it is a transient server error that may recover."
        ),
    )


# ---------------------------------------------------------------------------
# ToolResilience capability
# ---------------------------------------------------------------------------


@dataclass
class ToolResilience(AbstractCapability[AgentDeps]):
    """Route each tool execution error to a recovery strategy by its category.

    A transient error raises ModelRetry. Every other category returns a
    directive string as the tool result.
    """

    search_lookup_tools: frozenset[str] = frozenset()
    circuit_break_threshold: int = DEFAULT_CIRCUIT_BREAK_THRESHOLD

    async def on_tool_validate_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: Any,
        error: PydanticValidationError | ModelRetry,
    ) -> Any:
        del ctx, call
        if isinstance(error, PydanticValidationError):
            hint = _shape_error_hint(tool_def.name, args, error)
            if hint is not None:
                raise ModelRetry(hint) from error
        raise error

    async def on_tool_execute_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        error: Exception,
    ) -> Any:
        """Intercept tool execution errors and route by category."""
        # GraphInterrupt is a LangGraph control-flow signal, not an error.
        if isinstance(error, GraphInterrupt):
            raise error
        tool_name = tool_def.name
        category = classify_error(error)

        if category == ErrorCategory.TRANSIENT:
            search_name = _TransientArgs.model_validate(args).search_name
            if search_name is not None:
                seen = ctx.deps.service_outage.record_search_failure(search_name)
                if seen >= OUTAGE_GIVE_UP_THRESHOLD:
                    return _outage_directive(tool_name, search_name, error)
            retry_message = (
                f"Transient error in {tool_name}: {error}. "
                "The service may be temporarily unavailable. Retrying."
            )
            raise ModelRetry(retry_message)

        if category == ErrorCategory.SEMANTIC:
            return _semantic_directive(error, tool_name, args, self.search_lookup_tools)

        if category == ErrorCategory.PERMANENT:
            return build_error_directive(
                error_type="SERVICE_UNAVAILABLE",
                tool_name=tool_name,
                tool_args=args,
                detail=str(error),
                next_actions=_NEXT_ACTIONS_PERMANENT,
                do_not="Do not call this tool again — the service is permanently unavailable",
            )

        logger.error(
            "Unknown tool error",
            tool_name=tool_name,
            error_type=type(error).__name__,
            traceback=traceback.format_exc(),
        )
        return build_error_directive(
            error_type="INTERNAL_TOOL_ERROR",
            tool_name=tool_name,
            tool_args=args,
            detail=f"{type(error).__name__}: {error}",
            next_actions=_NEXT_ACTIONS_UNKNOWN,
            do_not="Do not retry this exact call — an unexpected internal error occurred",
        )

    async def prepare_tools(
        self,
        ctx: RunContext[AgentDeps],
        tool_defs: list[ToolDefinition],
    ) -> list[ToolDefinition]:
        """Remove tools whose retry count reaches the circuit-break threshold."""
        if not ctx.retries:
            return tool_defs

        filtered = [
            td
            for td in tool_defs
            if ctx.retries.get(td.name, 0) < self.circuit_break_threshold
        ]

        removed = [td.name for td in tool_defs if td not in filtered]
        if removed:
            logger.warning(
                "Circuit breaker: removing tools past retry threshold",
                removed_tools=removed,
                threshold=self.circuit_break_threshold,
            )

        return filtered
