"""HTTP route for the researcher's own datasets, read from VEuPathDB as they stand."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from pathfinder.services.eda.private_datasets import own_datasets
from pathfinder.transport.http.deps import (
    AvailableSite,
    CurrentUser,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas.eda_datasets import EdaOwnDatasetListResponse

router = APIRouter(
    prefix="/api/v1/eda/datasets",
    tags=["eda"],
    dependencies=[Depends(require_registered_wdk_identity)],
)


@router.get("", response_model=EdaOwnDatasetListResponse)
async def list_own_datasets(
    site_id: AvailableSite,
    user_id: CurrentUser,
) -> EdaOwnDatasetListResponse:
    """The researcher's count uploads on this site, and the site page that takes new ones."""
    del user_id
    found = await own_datasets(site_id)
    return EdaOwnDatasetListResponse.model_validate(found, from_attributes=True)
