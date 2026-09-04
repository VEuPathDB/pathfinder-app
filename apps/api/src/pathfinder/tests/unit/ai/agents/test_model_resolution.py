from __future__ import annotations

from pathfinder.ai.agents._model_resolution import resolve_orchestrator_model_entry


def test_resolve_with_explicit_id() -> None:
    entry = resolve_orchestrator_model_entry(
        model_id="openai:gpt-4.1-mini",
        provider=None,
    )
    assert "gpt" in entry.id.lower()


def test_resolve_with_unknown_id_falls_back() -> None:
    entry = resolve_orchestrator_model_entry(
        model_id="unknown:fake-model",
        provider=None,
    )
    # A fallback to a smallest-of-default provider still names a model.
    assert entry.id != ""
