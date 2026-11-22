"""Saving a dataset source in the signed-in account on one site."""

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter, Depends
from veupathdb.wdk.wdk_models import WDKDatasetConfig

from strategist.services.strategies.dataset_sources import saved_dataset
from strategist.transport.http.deps import (
    AvailableSite,
    require_registered_wdk_identity,
)

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


class SavedDataset(CamelModel):
    dataset_id: str


@router.post(
    "/{siteId}/datasets",
    response_model=SavedDataset,
    dependencies=[Depends(require_registered_wdk_identity)],
)
async def save_dataset(siteId: AvailableSite, source: WDKDatasetConfig) -> SavedDataset:
    """Save the source as a dataset an input-dataset parameter takes by its id."""
    saved = await saved_dataset(siteId, source)
    return SavedDataset(dataset_id=saved.dataset_id)
