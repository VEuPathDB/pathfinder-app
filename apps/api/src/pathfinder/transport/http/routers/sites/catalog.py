"""Site listing, record types, and search catalog endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query
from veupathdb_mcp import catalog

from pathfinder.platform.readiness import get_readiness
from pathfinder.transport.http.deps import AvailableSite
from pathfinder.transport.http.schemas import (
    RecordTypeResponse,
    SearchResponse,
    SiteResponse,
)

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


def _availability(site_id: str) -> tuple[bool, str | None]:
    """Whether the site's catalog is loaded, and why it is not."""
    reason = get_readiness().catalog_unavailable_reason(site_id)
    return reason is None, reason


@router.get("", response_model=list[SiteResponse])
async def list_sites() -> list[SiteResponse]:
    """List every VEuPathDB site, and say which ones answer."""
    sites = await catalog.list_sites()
    responses: list[SiteResponse] = []
    for s in sites:
        available, reason = _availability(s.id)
        responses.append(
            SiteResponse.model_validate(
                {
                    "id": s.id,
                    "name": s.name,
                    "displayName": s.display_name,
                    "baseUrl": s.base_url,
                    "projectId": s.project_id,
                    "isPortal": s.is_portal,
                    "available": available,
                    "unavailableReason": reason,
                }
            )
        )
    return responses


@router.get("/{siteId}/record-types", response_model=list[RecordTypeResponse])
async def get_record_types(siteId: AvailableSite) -> list[RecordTypeResponse]:
    """Get record types available on a site."""
    record_types = await catalog.get_record_types(siteId)
    return [
        RecordTypeResponse.model_validate(
            {
                "name": rt.name,
                "displayName": rt.display_name,
                "description": rt.description,
            }
        )
        for rt in record_types
    ]


@router.get("/{siteId}/searches", response_model=list[SearchResponse])
async def get_searches(
    siteId: AvailableSite,
    record_type: Annotated[str | None, Query(alias="recordType")] = None,
) -> list[SearchResponse]:
    """Get searches available on a site, optionally filtered by record type."""
    if record_type:
        searches = await catalog.list_searches(siteId, record_type)
        return [
            SearchResponse.model_validate(
                {
                    "name": s["name"],
                    "displayName": s["displayName"],
                    "recordType": record_type,
                }
            )
            for s in searches
        ]

    record_types = await catalog.get_raw_record_types(siteId)
    all_searches: list[SearchResponse] = []

    for rt in record_types:
        rt_name = rt.url_segment
        if rt_name:
            searches = await catalog.list_searches(siteId, rt_name)
            all_searches.extend(
                SearchResponse.model_validate(
                    {
                        "name": s["name"],
                        "displayName": s["displayName"],
                        "recordType": rt_name,
                    }
                )
                for s in searches
            )

    return all_searches
