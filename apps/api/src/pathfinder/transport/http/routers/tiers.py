"""Tiers endpoint - exposes tier preset registry to the frontend."""

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider, TierName
from fastapi import APIRouter

from pathfinder.platform.tiers import TIER_PRESETS, TierPreset


class TierListResponse(CamelModel):
    """Response for GET /api/v1/tiers."""

    presets: dict[str, dict[ModelProvider, dict[TierName, TierPreset]]]


router = APIRouter(prefix="/api/v1", tags=["tiers"])


@router.get("/tiers")
async def list_tiers() -> TierListResponse:
    """Return tier presets grouped by assistant, then by provider."""
    return TierListResponse(presets=TIER_PRESETS)
