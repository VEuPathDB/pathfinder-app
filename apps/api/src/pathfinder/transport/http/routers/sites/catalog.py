"""Site listing, record types, and search catalog endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query

from pathfinder.services import catalog
from pathfinder.transport.http.schemas import (
    RecordTypeResponse,
    SearchResponse,
    SiteResponse,
)

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


@router.get("", response_model=list[SiteResponse])
async def list_sites() -> list[SiteResponse]:
    """List all available VEuPathDB sites."""
    sites = await catalog.list_sites()
    return [
        SiteResponse.model_validate(
            {
                "id": s.id,
                "name": s.name,
                "displayName": s.display_name,
                "baseUrl": s.base_url,
                "projectId": s.project_id,
                "isPortal": s.is_portal,
            }
        )
        for s in sites
    ]


@router.get("/{siteId}/record-types", response_model=list[RecordTypeResponse])
async def get_record_types(siteId: str) -> list[RecordTypeResponse]:
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
    siteId: str,
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
