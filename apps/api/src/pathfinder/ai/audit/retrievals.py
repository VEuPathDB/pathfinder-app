"""The served research reads of an audit turn, each reference they return held as a read a verdict may cite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.toolsets import WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.lead.retrieval_toolset import RESEARCH_TOOLS, ResearchAnswer


@dataclass
class AuditRetrievalToolset(WrapperToolset[AuditDeps]):
    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[AuditDeps],
        tool: ToolsetTool[AuditDeps],
    ) -> Any:
        result = await super().call_tool(name, tool_args, ctx, tool)
        if name in RESEARCH_TOOLS:
            ctx.deps.reads |= set(ResearchAnswer.model_validate(result).references())
        return result
