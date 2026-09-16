"""The signed-in account's own WDK strategies on one site."""

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter, Depends
from veupathdb.wdk import get_strategy_api
from veupathdb.wdk.strategy_api.helpers import is_internal_wdk_strategy_name

from pathfinder.transport.http.deps import (
    AvailableSite,
    require_registered_wdk_identity,
)

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


class WdkStrategyListItem(CamelModel):
    """One strategy a researcher can open, as a picker draws it."""

    wdk_strategy_id: int
    name: str
    estimated_size: int | None = None
    is_saved: bool = False
    # WDK writes a local date-time with no zone, so the newest sorts last.
    last_modified: str = ""


@router.get(
    "/{siteId}/strategies",
    response_model=list[WdkStrategyListItem],
    dependencies=[Depends(require_registered_wdk_identity)],
)
async def list_account_strategies(siteId: AvailableSite) -> list[WdkStrategyListItem]:
    """List the signed-in account's strategies on this site, newest first.

    A strategy the researcher deleted, and a helper strategy this deployment
    wrote into the same account, are not the researcher's to reopen.
    """
    summaries = await get_strategy_api(siteId).list_strategies()
    return sorted(
        (
            WdkStrategyListItem(
                wdk_strategy_id=summary.strategy_id,
                name=summary.name,
                estimated_size=summary.estimated_size,
                is_saved=summary.is_saved,
                last_modified=summary.last_modified,
            )
            for summary in summaries
            if not summary.is_deleted
            and not is_internal_wdk_strategy_name(summary.name)
        ),
        key=lambda item: item.last_modified,
        reverse=True,
    )
