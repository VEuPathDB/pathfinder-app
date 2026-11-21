from __future__ import annotations

from pydantic import TypeAdapter
from veupathdb.wdk import get_strategy_api
from veupathdb_mcp.wdk import view_filters_for

_WEIGHT_COLUMN = "wdk_weight"
_COUNTS: TypeAdapter[dict[int, int]] = TypeAdapter(dict[int, int])


async def count_weights(
    site_id: str, wdk_step_id: int, record_type: str | None
) -> dict[int, int]:
    histogram = await get_strategy_api(site_id).get_step_histogram(
        wdk_step_id, _WEIGHT_COLUMN, view_filters=view_filters_for(record_type)
    )
    return _COUNTS.validate_python(histogram.data)


__all__ = ["count_weights"]
