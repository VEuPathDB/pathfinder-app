"""Models endpoint - exposes available LLM models and their status."""

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider, TierName
from assistant_core.pricing import lookup_per_mtok_prices
from fastapi import APIRouter
from pydantic import ConfigDict

from pathfinder.assistants.registry import installed_phase_defaults
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_catalog import ModelEntry, get_model_catalog


class ModelCatalogEntryResponse(ModelEntry):
    """API response model - adds whether the deployment pays for the model."""

    model_config = ConfigDict(frozen=False)

    enabled: bool = True


class ModelListResponse(CamelModel):
    """Response for the /models endpoint."""

    models: list[ModelCatalogEntryResponse]
    default_provider: ModelProvider
    default_tier: TierName
    phase_defaults: dict[str, str]


router = APIRouter(prefix="/api/v1", tags=["models"])


def _build_response_entry(entry: ModelEntry) -> ModelCatalogEntryResponse:
    """The catalog entry as served: an entry the snapshot meters shows the
    snapshot's live price, and one the catalog meters shows its own."""
    payload = entry.model_dump()
    if entry.meter is None:
        live = lookup_per_mtok_prices(entry.provider, entry.model_name)
        if live.input_ is not None:
            payload["input_price"] = live.input_
        if live.cached_input is not None:
            payload["cached_input_price"] = live.cached_input
        if live.output is not None:
            payload["output_price"] = live.output
    return ModelCatalogEntryResponse(
        **payload,
        enabled=entry.deployment_may_pay
        and entry.provider in get_settings().deployment_providers,
    )


@router.get("/models")
async def list_models() -> ModelListResponse:
    """Return available models grouped by provider.

    An entry the catalog meters shows the catalog's prices, the ones the spend
    meter charges; any other entry shows the live ``genai_prices`` snapshot
    price, with the catalog's value where the snapshot has none. A model the
    deployment does not pay for is returned with ``enabled: false``: its
    provider holds no deployment key, or its entry runs only on a researcher's
    own key. That key is read from ``/api/v1/me/provider-keys``, because this
    route answers before sign-in.
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
        phase_defaults=installed_phase_defaults(
            settings.default_provider, settings.default_tier
        ),
    )
