from __future__ import annotations

from assistant_core.platform.types import ModelProvider

from pathfinder.platform.config import get_settings
from pathfinder.platform.model_catalog import (
    ModelEntry,
    get_model_entry,
    get_smallest_model,
)


def resolve_orchestrator_model_entry(
    model_id: str | None,
    provider: ModelProvider | None,
) -> ModelEntry:
    """Pick the orchestrator/compactor's model entry.

    Precedence: explicit catalog id -> explicit provider's smallest ->
    configured default provider's smallest.
    """
    if model_id is not None:
        entry = get_model_entry(model_id)
        if entry is not None:
            return entry
    resolved_provider: ModelProvider = provider or get_settings().default_provider
    return get_smallest_model(resolved_provider)
