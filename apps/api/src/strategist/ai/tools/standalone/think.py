"""Think tool - explicit reasoning scratchpad between tool calls."""

from assistant_core.graph.tool_summary import truncate_summary, with_summary
from pydantic_ai.messages import ToolReturn
from pydantic_ai.tools import RunContext

from strategist.ai.graph.runtime import AgentDeps


async def think(ctx: RunContext[AgentDeps], thought: str) -> ToolReturn[str]:
    """Use this to think step-by-step about your approach, reflect on
    intermediate results, or reason about what to do next. Call this
    between other tool calls when facing complex decisions."""
    line = truncate_summary(thought) or "No thought written"
    return with_summary(thought, line, ctx=ctx)
