"""The signed-in account's own WDK strategies on one site."""

from __future__ import annotations

from veupathdb.wdk import WDKStrategySummary, get_strategy_api
from veupathdb.wdk.strategy_api.helpers import is_internal_wdk_strategy_name


async def account_strategies(site_id: str) -> list[WDKStrategySummary]:
    summaries = await get_strategy_api(site_id).list_strategies()
    return sorted(
        (
            summary
            for summary in summaries
            if not summary.is_deleted
            and not is_internal_wdk_strategy_name(summary.name)
        ),
        key=lambda summary: summary.last_modified,
        reverse=True,
    )
