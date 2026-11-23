from __future__ import annotations

from veupathdb_mcp.catalog import DecisionRequest, DecisionResponse


async def no_decision(request: DecisionRequest) -> DecisionResponse | None:
    del request
    return None
