from __future__ import annotations

from uuid import uuid4

import pytest

from strategist.ai.agents.registry import phase_defaults
from strategist.ai.conversation.request_body import ChatRequestBody
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.platform.model_catalog import (
    EXPLORE_MODELS,
    deployment_may_pay,
    get_model_catalog,
)
from strategist.platform.model_entry import require_catalogued
from strategist.platform.tiers import (
    EXPLORE_ROLE,
    KNOWN_ROLES,
    OWN_KEY_TIER_PRESETS,
    TIER_PRESETS,
    TierPreset,
)

BALANCED_BEFORE = {
    "lead": "openai:gpt-5.6-luna",
    "frame": "openai:gpt-5.6-luna",
    "execution": "openai:gpt-6-luna",
    "verification": "openai:gpt-6-luna",
}


_EXPLORES_ON = {
    "openai": {
        "fast": "openai:gpt-5.6-luna",
        "default": "openai:gpt-5.6-luna",
        "balanced": "openai:gpt-6.1-terra",
        "quality": "openai:gpt-6.1-sol",
    },
    "anthropic": {
        "fast": "anthropic:claude-haiku-5-5",
        "default": "anthropic:claude-haiku-5-5",
        "balanced": "anthropic:claude-sonnet-5-5",
        "quality": "anthropic:claude-sonnet-5-5",
    },
    "google": {
        "fast": "google:gemini-3.5-flash-lite",
        "default": "google:gemini-3.5-flash-lite",
        "balanced": "google:gemini-3.8-flash",
        "quality": "google:gemini-4-argon",
    },
}


@pytest.mark.parametrize("presets", [TIER_PRESETS, OWN_KEY_TIER_PRESETS])
def test_each_tier_explores_on_its_decided_model(
    presets: dict[str, dict[str, dict[str, TierPreset]]],
) -> None:
    explores_on = {
        provider: {
            name: preset.roles["explore"].model_id for name, preset in tiers.items()
        }
        for provider, tiers in presets[STRATEGIST_ASSISTANT_ID].items()
    }
    assert explores_on == _EXPLORES_ON


def test_explore_runs_at_the_thinker_effort() -> None:
    for name, preset in TIER_PRESETS[STRATEGIST_ASSISTANT_ID]["openai"].items():
        assert preset.roles["explore"].reasoning_effort == (
            preset.roles["lead"].reasoning_effort
        ), name


def test_the_deployment_never_pays_for_a_model_it_may_not() -> None:
    for provider, tiers in TIER_PRESETS[STRATEGIST_ASSISTANT_ID].items():
        for preset in tiers.values():
            assert deployment_may_pay(preset.roles["explore"].model_id), provider


def test_no_existing_role_moves() -> None:
    roles = TIER_PRESETS[STRATEGIST_ASSISTANT_ID]["openai"]["balanced"].roles
    assert {r: c.model_id for r, c in roles.items() if r != "explore"} == (
        BALANCED_BEFORE
    )


def test_the_explore_role_is_known() -> None:
    assert EXPLORE_ROLE == "explore"
    assert EXPLORE_ROLE in KNOWN_ROLES


def test_the_explore_role_has_a_compile_time_model() -> None:
    assert phase_defaults()["explore"] == EXPLORE_MODELS["openai"]["default"]


def test_a_chat_body_may_pick_an_explore_model() -> None:
    body = ChatRequestBody.model_validate(
        {
            "conversationId": str(uuid4()),
            "phaseModels": {"explore": "anthropic:claude-fable-5-1"},
        }
    )
    assert body.runtime_phase_models == {"explore": "anthropic:claude-fable-5-1"}


def test_a_model_the_catalog_lacks_is_refused() -> None:
    with pytest.raises(ValueError, match="openai:gpt-none"):
        require_catalogued({"openai": "openai:gpt-none"}, get_model_catalog())


def test_catalogued_models_pass() -> None:
    models = {"openai": "openai:gpt-6.1-terra"}
    assert require_catalogued(models, get_model_catalog()) == models
