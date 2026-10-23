"""Thesis evaluation endpoints - materialize gold strategies and fetch gene IDs.

Thin HTTP adapter; all business logic lives in
``pathfinder.services.eval``.

Read-only from the application's perspective (creates WDK strategies but does
not affect PathFinder's own data).  Used by thesis/eval/scripts/ only.
"""

from typing import Any
from uuid import UUID

from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter, Depends
from pydantic import Field

from pathfinder.platform.uuid_utils import format_uuid
from pathfinder.services.eval import (
    build_gold_strategy,
    get_strategy_gene_ids,
)
from pathfinder.transport.http.deps import (
    CurrentUser,
    DBSession,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas.site_id import SiteId

# Both routes build or read a WDK strategy in the caller's own account.
router = APIRouter(
    prefix="/api/v1/eval",
    tags=["eval"],
    dependencies=[Depends(require_registered_wdk_identity)],
)
logger = get_logger(__name__)


class BuildGoldRequest(CamelModel):
    """Request to materialize a gold strategy AST on WDK and return gene IDs."""

    gold_id: str
    site_id: SiteId
    step_tree: dict[str, Any]
    dataset_gene_ids: dict[str, list[str]] | None = Field(default=None)


class BuildGoldResponse(CamelModel):
    gold_id: str
    wdk_strategy_id: int
    root_step_id: int
    estimated_size: int
    gene_ids: list[str]
    conversation_id: str | None = Field(default=None)


@router.post("/build-gold", response_model=BuildGoldResponse)
async def build_gold_strategy_endpoint(
    request: BuildGoldRequest,
    user_id: CurrentUser,
) -> BuildGoldResponse:
    """Materialize a gold strategy AST on WDK and fetch all result gene IDs."""
    result = await build_gold_strategy(
        gold_id=request.gold_id,
        site_id=request.site_id,
        step_tree=request.step_tree,
        dataset_gene_ids=request.dataset_gene_ids,
        user_id=user_id,
    )
    return BuildGoldResponse(
        gold_id=result.gold_id,
        wdk_strategy_id=result.wdk_strategy_id,
        root_step_id=result.root_step_id,
        estimated_size=len(result.gene_ids),
        gene_ids=result.gene_ids,
        conversation_id=format_uuid(result.conversation_id),
    )


class FetchGeneIdsRequest(CamelModel):
    """Fetch gene IDs from an existing PathFinder strategy."""

    strategy_id: UUID
    site_id: SiteId


@router.post("/strategy-gene-ids")
async def strategy_gene_ids_endpoint(
    request: FetchGeneIdsRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> dict[str, Any]:
    """Fetch all gene IDs from a PathFinder strategy's WDK root step."""
    result = await get_strategy_gene_ids(
        session,
        request.strategy_id,
        request.site_id,
        user_id,
    )
    return result.model_dump(by_alias=True, exclude_none=True)
