"""The model one site-help turn runs on: the user pick, the tier, then the baked id."""

from __future__ import annotations

import pytest
from assistant_core.platform.context import PhaseOverrides, attach_phase_overrides
from pydantic_ai.models.function import FunctionModel

from pathfinder.assistants.site_help.agent import SITE_HELP_MODEL, turn_model
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID


@pytest.fixture
def _cloud_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_tier", "quality", raising=False)


def test_the_mock_provider_swaps_the_whole_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        get_settings(), "pathfinder_chat_provider", "mock", raising=False
    )

    model, model_settings = turn_model()

    assert isinstance(model, FunctionModel)
    assert (model.model_name, model.system, model_settings) == (
        "mock:deterministic",
        "function",
        None,
    )


@pytest.mark.usefixtures("_cloud_provider")
def test_the_configured_tier_moves_the_model() -> None:
    model, model_settings = turn_model()

    assert model == "openai:gpt-5.6-terra"
    assert model != SITE_HELP_MODEL
    assert model_settings is not None
    assert model_settings.get("thinking") == "medium"


@pytest.mark.usefixtures("_cloud_provider")
def test_a_user_pick_for_the_role_wins_over_the_tier() -> None:
    overrides = PhaseOverrides(
        models={SITE_HELP_ASSISTANT_ID: "openai:gpt-5.6-sol"},
        reasoning={SITE_HELP_ASSISTANT_ID: "high"},
    )

    with attach_phase_overrides(overrides):
        model, model_settings = turn_model()

    assert model == "openai:gpt-5.6-sol"
    assert model_settings is not None
    assert model_settings.get("thinking") == "high"


@pytest.mark.usefixtures("_cloud_provider")
def test_a_pick_for_another_role_leaves_this_turn_alone() -> None:
    with attach_phase_overrides(
        PhaseOverrides(models={"execution": "openai:gpt-5.6-sol"}),
    ):
        model, _ = turn_model()

    assert model == "openai:gpt-5.6-terra"


def test_a_provider_with_no_presets_falls_back_to_the_baked_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_provider", "ollama", raising=False)
    monkeypatch.setattr(settings, "default_tier", "quality", raising=False)

    model, model_settings = turn_model()

    assert model == SITE_HELP_MODEL
    assert model_settings is not None
    assert "thinking" not in model_settings
