from __future__ import annotations

from strategist.ai.agents._model_resolution import resolve_orchestrator_model_entry
from strategist.platform.config import get_settings
from strategist.platform.model_catalog import get_smallest_model
from strategist.tests._support.models import OPENAI_FLAGSHIP


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
