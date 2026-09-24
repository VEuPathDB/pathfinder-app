"""Execution-phase toolset - declarative strategy build + atomic edits."""

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.tools import RunContext, Tool, ToolDefinition
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.prepared import PreparedToolset

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.conversation import rename_strategy
from pathfinder.ai.tools.standalone.escape_hatch import (
    request_search_inspection,
)
from pathfinder.ai.tools.standalone.memory_tools import remember, search_memory
from pathfinder.ai.tools.standalone.strategy import (
    apply_operations,
    build_strategy,
)
from pathfinder.ai.tools.standalone.strategy_attach import (
    add_step_filter,
    add_step_report,
)
from pathfinder.ai.tools.standalone.strategy_edits import (
    delete_step,
    insert_saved_strategy,
    replace_subtree,
    update_combine_operator,
    update_leaf_params,
    update_step_metadata,
)
from pathfinder.ai.tools.standalone.strategy_graph import get_strategy
from pathfinder.ai.tools.standalone.think import think
from pathfinder.ai.tools.toolsets._dynamic import (
    DynamicEnumToolset,
    EnumOverrides,
    live_step_ids,
)

_MAX_CONSECUTIVE_GET_STRATEGY = 2


def _get_strategy_repeated_without_mutation(
    ctx: RunContext[AgentDeps],
) -> bool:
    """True when the last calls in history are ``get_strategy`` repeated
    ≥ N times with no other tool between them. Any non-``get_strategy``
    call breaks the streak.
    """
    consecutive = 0
    for msg in reversed(ctx.messages):
        if not isinstance(msg, ModelResponse):
            continue
        for part in reversed(msg.parts):
            if not isinstance(part, ToolCallPart):
                continue
            if part.tool_name == "get_strategy":
                consecutive += 1
                if consecutive >= _MAX_CONSECUTIVE_GET_STRATEGY:
                    return True
            else:
                return False
    return False


async def _prepare(
    ctx: RunContext[AgentDeps],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    if _get_strategy_repeated_without_mutation(ctx):
        return [td for td in tool_defs if td.name != "get_strategy"]
    return tool_defs


def _execution_enum_overrides(
    ctx: RunContext[AgentDeps],
) -> EnumOverrides:
    """Constrain step-id args on edit tools to live-graph reality.

    The model literally cannot reference a step that doesn't exist in
    the strategy right now. ``build_strategy`` and ``replace_subtree``
    construct fresh subtrees so they are not constrained here.
    """
    overrides: EnumOverrides = {}
    step_ids = live_step_ids(ctx.deps)
    if step_ids:
        for tool, arg in (
            ("update_leaf_params", "step_id"),
            ("update_combine_operator", "step_id"),
            ("update_step_metadata", "step_id"),
            ("delete_step", "step_id"),
            ("replace_subtree", "step_id"),
            ("insert_saved_strategy", "target_step_id"),
            ("add_step_filter", "step_id"),
            ("add_step_report", "step_id"),
        ):
            overrides[(tool, arg)] = step_ids
    return overrides


def build_toolset() -> AbstractToolset[AgentDeps]:
    base = FunctionToolset[AgentDeps](
        max_retries=3,
        tools=[
            apply_operations,
            build_strategy,
            update_leaf_params,
            update_combine_operator,
            update_step_metadata,
            Tool(delete_step, requires_approval=True, max_retries=3),
            Tool(replace_subtree, requires_approval=True, max_retries=3),
            insert_saved_strategy,
            add_step_filter,
            add_step_report,
            rename_strategy,
            get_strategy,
            request_search_inspection,
            think,
            search_memory,
            remember,
        ],
    )
    return DynamicEnumToolset(
        wrapped=PreparedToolset(wrapped=base, prepare_func=_prepare),
        build_overrides=_execution_enum_overrides,
    )
