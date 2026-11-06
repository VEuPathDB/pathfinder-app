from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.agents.registry import phase_defaults
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.model_catalog import (
    EXPLORE_MODELS,
    deployment_may_pay,
    get_model_catalog,
)
from pathfinder.platform.model_entry import require_catalogued
from pathfinder.platform.tiers import (
    EXPLORE_ROLE,
    KNOWN_ROLES,
    OWN_KEY_TIER_PRESETS,
    TIER_PRESETS,
)

BALANCED_BEFORE = {
    "lead": "openai:gpt-5.6-luna",
    "frame": "openai:gpt-5.6-luna",
    "execution": "openai:gpt-6-luna",
    "verification": "openai:gpt-6-luna",
}


def test_every_openai_tier_explores_on_terra() -> None:
    for name, preset in TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["openai"].items():
        assert preset.roles["explore"].model_id == "openai:gpt-6.1-terra", name


def test_every_google_tier_explores_on_argon() -> None:
    for name, preset in TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["google"].items():
        assert preset.roles["explore"].model_id == "google:gemini-4-argon", name


def test_explore_runs_at_the_thinker_effort() -> None:
    preset = TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["openai"]["fast"]
    assert preset.roles["explore"].reasoning_effort == "low"
    assert preset.roles["explore"].reasoning_effort == (
        preset.roles["lead"].reasoning_effort
    )


def test_an_own_anthropic_key_explores_on_opus() -> None:
    preset = OWN_KEY_TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["anthropic"]["quality"]
    assert preset.roles["explore"].model_id == "anthropic:claude-opus-5-5"


def test_a_deployment_paid_anthropic_turn_explores_on_the_thinker() -> None:
    for name, preset in TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["anthropic"].items():
        assert preset.roles["explore"] == preset.roles["lead"], name


def test_the_deployment_never_pays_for_a_model_it_may_not() -> None:
    for provider, tiers in TIER_PRESETS[PATHFINDER_ASSISTANT_ID].items():
        for preset in tiers.values():
            assert deployment_may_pay(preset.roles["explore"].model_id), provider


def test_no_existing_role_moves() -> None:
    roles = TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["openai"]["balanced"].roles
    assert {r: c.model_id for r, c in roles.items() if r != "explore"} == (
        BALANCED_BEFORE
    )


def test_the_explore_role_is_known() -> None:
    assert EXPLORE_ROLE == "explore"
    assert EXPLORE_ROLE in KNOWN_ROLES


def test_the_explore_role_has_a_compile_time_model() -> None:
    assert phase_defaults()["explore"] == EXPLORE_MODELS["openai"]


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
