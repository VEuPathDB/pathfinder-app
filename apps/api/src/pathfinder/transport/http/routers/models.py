"""Models endpoint - exposes available LLM models and their status."""

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider, TierName
from assistant_core.pricing import lookup_per_mtok_prices
from fastapi import APIRouter
from pydantic import ConfigDict

from pathfinder.ai.models.catalog import ModelEntry, get_model_catalog
from pathfinder.assistants.registry import installed_phase_defaults
from pathfinder.platform.config import get_settings


class ModelCatalogEntryResponse(ModelEntry):
    """API response model - adds ``enabled`` status per provider configuration."""

    model_config = ConfigDict(frozen=False)

    enabled: bool = True


class ModelListResponse(CamelModel):
    """Response for the /models endpoint."""

    models: list[ModelCatalogEntryResponse]
    default_provider: ModelProvider
    default_tier: TierName
    phase_defaults: dict[str, str]


router = APIRouter(prefix="/api/v1", tags=["models"])


def _provider_enabled(provider: ModelProvider) -> bool:
    """Check whether a model provider has its API key configured.

    :param provider: Model provider.
    :returns: True if the provider is enabled, False otherwise.
    """
    settings = get_settings()
    key_map: dict[ModelProvider, str] = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "google": settings.gemini_api_key,
        "ollama": settings.ollama_base_url,
    }
    return bool(key_map.get(provider, ""))


def _build_response_entry(entry: ModelEntry) -> ModelCatalogEntryResponse:
    """Overlay live genai-prices on the catalog entry, falling back to catalog values."""
    live = lookup_per_mtok_prices(entry.provider, entry.model_name)
    payload = entry.model_dump()
    if live.input_ is not None:
        payload["input_price"] = live.input_
    if live.cached_input is not None:
        payload["cached_input_price"] = live.cached_input
    if live.output is not None:
        payload["output_price"] = live.output
    return ModelCatalogEntryResponse(
        **payload,
        enabled=_provider_enabled(entry.provider),
    )


@router.get("/models")
async def list_models() -> ModelListResponse:
    """Return available models grouped by provider.

    Prices overlay live ``genai_prices`` snapshot data when available; the
    catalog's hardcoded values act as a fallback for models the upstream
    library doesn't yet track. Models whose provider has no API key are
    returned with ``enabled: false`` so the frontend can render them as
    disabled in the picker.
    """
    settings = get_settings()
    is_mock = settings.pathfinder_chat_provider.strip().lower() == "mock"
    models = [
        _build_response_entry(m)
        for m in get_model_catalog()
        if is_mock or m.provider != "mock"
    ]
    return ModelListResponse(
        models=models,
        default_provider=settings.default_provider,
        default_tier=settings.default_tier,
        phase_defaults=installed_phase_defaults(),
    )
