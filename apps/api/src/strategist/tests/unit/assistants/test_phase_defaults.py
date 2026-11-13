"""The model every installed role runs on when the user pins nothing."""

from __future__ import annotations

import pytest

from strategist.ai.agents.registry import phase_defaults
from strategist.ai.audit.auditor import audit_compile_time_models
from strategist.assistants.registry import (
    assistant_role_models,
    installed_phase_defaults,
    prompt_reader_model,
)
from strategist.platform.config import get_settings
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.platform.model_catalog import EXPLORE_MODELS
from strategist.tests._support.models import (
    ANTHROPIC_SMALL,
    DEFAULT_MODEL,
    GOOGLE_FLAGSHIP,
    GOOGLE_STANDARD,
    OPENAI_SMALL,
    OPENAI_STANDARD,
)
from strategist.tests._support.second_assistant import (
    HELPER,
    HELPER_MODEL,
    second_assistant,
)

OPENAI_EXPLORE = EXPLORE_MODELS["openai"]


def test_a_split_tier_answers_the_model_of_each_role() -> None:
    """The reasoning roles take the thinker model, the builder the worker one."""
    defaults = installed_phase_defaults("openai", "balanced")

    assert defaults == {
        "lead": OPENAI_STANDARD,
        "frame": OPENAI_STANDARD,
        "execution": OPENAI_SMALL,
        "verification": OPENAI_SMALL,
        "explore": OPENAI_EXPLORE["balanced"],
        "auditor": OPENAI_STANDARD,
        "audit_review": OPENAI_SMALL,
    }


def test_a_uniform_tier_answers_one_model_for_every_role_but_explore() -> None:
    defaults = installed_phase_defaults("openai", "fast")

    assert set(defaults) == set(phase_defaults()) | {"auditor", "audit_review"}
    assert defaults["explore"] == OPENAI_EXPLORE["fast"]
    assert {m for r, m in defaults.items() if r != "explore"} == {OPENAI_SMALL}


def test_another_provider_answers_that_provider_models() -> None:
    defaults = installed_phase_defaults("google", "quality")

    assert defaults["lead"] == GOOGLE_FLAGSHIP
    assert defaults["execution"] == GOOGLE_STANDARD


def test_a_role_no_tier_names_keeps_its_compile_time_model() -> None:
    """``custom`` means per-role user picks, so no preset resolves it."""
    defaults = installed_phase_defaults("openai", "custom")

    assert defaults == phase_defaults() | audit_compile_time_models()


def test_a_provider_without_presets_keeps_the_compile_time_models() -> None:
    defaults = installed_phase_defaults("ollama", "balanced")

    assert defaults == phase_defaults() | audit_compile_time_models()


def test_one_assistant_runs_each_of_its_roles_on_the_pick_or_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "default_provider", "openai")
    monkeypatch.setattr(settings, "default_tier", "default")

    roles = assistant_role_models(
        STRATEGIST_ASSISTANT_ID,
        {"lead": ANTHROPIC_SMALL, HELPER: "google:x"},
    )

    assert roles == {
        "lead": ANTHROPIC_SMALL,
        "frame": DEFAULT_MODEL,
        "execution": DEFAULT_MODEL,
        "verification": DEFAULT_MODEL,
        "explore": OPENAI_EXPLORE["default"],
    }


def test_a_second_assistant_adds_its_roles_to_the_installed_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production = installed_phase_defaults("openai", "balanced")

    with second_assistant(monkeypatch):
        defaults = installed_phase_defaults("openai", "balanced")

    assert defaults == {**production, HELPER: HELPER_MODEL}


def test_the_one_agent_assistant_has_one_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with second_assistant(monkeypatch):
        assert assistant_role_models(HELPER, {}) == {HELPER: HELPER_MODEL}
        assert assistant_role_models(HELPER, {HELPER: ANTHROPIC_SMALL}) == {
            HELPER: ANTHROPIC_SMALL
        }


def test_the_lead_reads_the_message_of_a_strategist_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "default_provider", "openai")
    monkeypatch.setattr(settings, "default_tier", "balanced")

    assert prompt_reader_model(STRATEGIST_ASSISTANT_ID, {}) == OPENAI_STANDARD
    assert (
        prompt_reader_model(STRATEGIST_ASSISTANT_ID, {"frame": "google:x"})
        == OPENAI_STANDARD
    )
    assert (
        prompt_reader_model(STRATEGIST_ASSISTANT_ID, {"lead": OPENAI_SMALL})
        == OPENAI_SMALL
    )


def test_the_one_agent_reads_the_message_of_its_own_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with second_assistant(monkeypatch):
        assert prompt_reader_model(HELPER, {}) == HELPER_MODEL
        assert prompt_reader_model(HELPER, {HELPER: GOOGLE_STANDARD}) == (
            GOOGLE_STANDARD
        )
