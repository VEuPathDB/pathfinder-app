from __future__ import annotations

import copy
from dataclasses import replace

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from strategist.ai.audit.deps import AuditDeps


async def genomes_of_the_site(
    ctx: RunContext[AuditDeps], tool_def: ToolDefinition
) -> ToolDefinition:
    organisms = await ctx.deps.organisms.of(ctx.deps.site_id)
    if organisms is None:
        return tool_def
    schema = copy.deepcopy(tool_def.parameters_json_schema)
    genomes = schema["properties"]["genomes"]
    if organisms:
        genomes["items"] = {"type": "string", "enum": list(organisms)}
    else:
        genomes["maxItems"] = 0
    return replace(tool_def, parameters_json_schema=schema)
