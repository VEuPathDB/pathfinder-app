from __future__ import annotations

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.tools import RunContext, ToolDefinition
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.prepared import PreparedToolset

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.scratchpad.tools import (
    delete_note,
    list_notes,
    note,
    pin_note,
    promote_to_memory,
    read_note,
    search_notes,
    unpin_note,
    update_note,
)
from pathfinder.services.conversations.scratchpad_service import (
    ScratchpadNotebook,
)

_EMPTY_SCRATCHPAD_HIDDEN = frozenset(
    {
        "list_notes",
        "search_notes",
        "read_note",
        "update_note",
        "delete_note",
        "pin_note",
        "unpin_note",
        "promote_to_memory",
    }
)

_SCRATCHPAD_READ_TOOLS = frozenset({"search_notes", "list_notes", "read_note"})

_MAX_CONSECUTIVE_READ = 2


def _loop_hidden_read_tools(ctx: RunContext[AgentDeps]) -> frozenset[str]:
    """Names of scratchpad read tools that should disappear this step
    because the agent called one of them twice in a row. Hiding forces the
    model to take a different action (``note``, ``set_criterion``, etc.)
    before searching again. Only the TAIL of history matters: any non-read
    tool (mutation or otherwise) breaks the streak and resets.
    """
    counts: dict[str, int] = {}
    for msg in reversed(ctx.messages):
        if not isinstance(msg, ModelResponse):
            continue
        for part in reversed(msg.parts):
            if not isinstance(part, ToolCallPart):
                continue
            if part.tool_name in _SCRATCHPAD_READ_TOOLS:
                counts[part.tool_name] = counts.get(part.tool_name, 0) + 1
                continue
            # Any other tool (mutation or unrelated) ends the read streak.
            return frozenset(
                {n for n, c in counts.items() if c >= _MAX_CONSECUTIVE_READ}
            )
    return frozenset({n for n, c in counts.items() if c >= _MAX_CONSECUTIVE_READ})


async def _prepare_scratchpad_tools(
    ctx: RunContext[AgentDeps],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    factory = ctx.deps.db_session_factory
    conversation_id = ctx.deps.conversation_id
    if factory is None or conversation_id is None:
        return tool_defs
    total = await ScratchpadNotebook(factory, conversation_id).total_notes()
    if total == 0:
        return [td for td in tool_defs if td.name not in _EMPTY_SCRATCHPAD_HIDDEN]
    loop_hidden = _loop_hidden_read_tools(ctx)
    if not loop_hidden:
        return tool_defs
    return [td for td in tool_defs if td.name not in loop_hidden]


def build_scratchpad_toolset() -> AbstractToolset[AgentDeps]:
    base = FunctionToolset[AgentDeps](
        max_retries=3,
        tools=[
            note,
            update_note,
            delete_note,
            pin_note,
            unpin_note,
            list_notes,
            search_notes,
            read_note,
            promote_to_memory,
        ],
    )
    return PreparedToolset(wrapped=base, prepare_func=_prepare_scratchpad_tools)
