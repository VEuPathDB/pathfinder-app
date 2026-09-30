from __future__ import annotations

from pathfinder.ai.agents._model_resolution import resolve_orchestrator_model_entry
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_catalog import get_smallest_model
from pathfinder.tests._support.models import OPENAI_FLAGSHIP


def test_resolve_with_explicit_id() -> None:
    entry = resolve_orchestrator_model_entry(
        model_id=OPENAI_FLAGSHIP,
        provider=None,
    )
    assert entry.id == OPENAI_FLAGSHIP


def test_resolve_with_unknown_id_falls_back() -> None:
    entry = resolve_orchestrator_model_entry(
        model_id="unknown:fake-model",
        provider=None,
    )
    assert entry == get_smallest_model(get_settings().default_provider)
