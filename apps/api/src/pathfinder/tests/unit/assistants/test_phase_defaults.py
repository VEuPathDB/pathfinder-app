"""The model every installed role runs on when the user pins nothing."""

from __future__ import annotations

from pathfinder.ai.agents.registry import phase_defaults
from pathfinder.assistants.registry import installed_phase_defaults
from pathfinder.assistants.site_help.agent import SITE_HELP_MODEL
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID


def test_a_split_tier_answers_the_model_of_each_role() -> None:
    """The reasoning roles take the thinker model, the builder the worker one."""
    defaults = installed_phase_defaults("openai", "balanced")

    assert defaults == {
        "lead": "openai:gpt-5.6-terra",
        "frame": "openai:gpt-5.6-terra",
        "execution": "openai:gpt-5.6-luna",
        "verification": "openai:gpt-5.6-terra",
        SITE_HELP_ASSISTANT_ID: "openai:gpt-5.6-luna",
    }


def test_a_uniform_tier_answers_one_model_for_every_role() -> None:
    defaults = installed_phase_defaults("openai", "default")

    assert set(defaults.values()) == {"openai:gpt-5.6-luna"}
    assert set(defaults) == set(phase_defaults()) | {SITE_HELP_ASSISTANT_ID}


def test_another_provider_answers_that_provider_models() -> None:
    defaults = installed_phase_defaults("anthropic", "quality")

    assert defaults["lead"] == "anthropic:claude-opus-5"
    assert defaults["execution"] == "anthropic:claude-sonnet-5"


def test_a_role_no_tier_names_keeps_its_compile_time_model() -> None:
    """``custom`` means per-role user picks, so no preset resolves it."""
    defaults = installed_phase_defaults("openai", "custom")

    assert defaults == {**phase_defaults(), SITE_HELP_ASSISTANT_ID: SITE_HELP_MODEL}


def test_a_provider_without_presets_keeps_the_compile_time_models() -> None:
    defaults = installed_phase_defaults("ollama", "balanced")

    assert defaults == {**phase_defaults(), SITE_HELP_ASSISTANT_ID: SITE_HELP_MODEL}
