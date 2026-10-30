from veupathdb.wdk import get_site

from pathfinder.domain.strategy.types import SyncStateProtocol

RESULT_LIST_TAB = "summary:_default"


def result_list_url(site_id: str, wdk_strategy_id: int, wdk_step_id: int | None) -> str:
    page = get_site(site_id).strategy_url(wdk_strategy_id, wdk_step_id)
    return page if wdk_step_id is None else f"{page}/{RESULT_LIST_TAB}"


def live_result_list_url(site_id: str, sync: SyncStateProtocol | None) -> str | None:
    if sync is None or sync.wdk_strategy_id is None:
        return None
    return result_list_url(site_id, sync.wdk_strategy_id, sync.wdk_root_step_id)
