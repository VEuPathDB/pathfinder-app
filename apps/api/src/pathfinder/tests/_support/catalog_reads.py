"""A catalog read the FRAME pass holds, as a listing tool records one."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.ai.agents.state import CatalogHit, CatalogRead


def listing(
    names: Sequence[str],
    *,
    record_type: str = "transcript",
    tool_call_id: str = "call_list",
) -> CatalogRead:
    """A ``list_searches`` answer naming these searches, in this order."""
    return CatalogRead(
        tool_call_id=tool_call_id,
        tool="list_searches",
        record_type=record_type,
        hits=[
            CatalogHit(name=name, display_name=name, record_type=record_type)
            for name in names
        ],
    )
