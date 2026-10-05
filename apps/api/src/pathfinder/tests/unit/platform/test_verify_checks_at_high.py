"""VERIFY checks at high effort on the model its tier gives BUILD; the default
tier runs every role on the provider's default model."""

from __future__ import annotations

import pytest
from assistant_core.platform.types import ModelProvider, TierName

from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.tiers import TIER_PRESETS, TierPreset

_TIERS = [
    (provider, name, preset)
    for provider, by_tier in TIER_PRESETS[PATHFINDER_ASSISTANT_ID].items()
    for name, preset in by_tier.items()
]


@pytest.mark.parametrize(("provider", "tier", "preset"), _TIERS)
def test_verify_checks_at_high_on_the_build_model(
    provider: ModelProvider, tier: TierName, preset: TierPreset
) -> None:
    del provider, tier
    verify = preset.roles["verification"]

    assert verify.reasoning_effort == "high"
    assert verify.model_id == preset.roles["execution"].model_id


def test_the_default_tier_runs_every_role_on_the_default_model() -> None:
    preset = TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["openai"]["default"]

    assert {
        role: (cfg.model_id, cfg.reasoning_effort) for role, cfg in preset.roles.items()
    } == {
        "lead": ("openai:gpt-5.6-luna", "medium"),
        "frame": ("openai:gpt-5.6-luna", "medium"),
        "execution": ("openai:gpt-5.6-luna", "medium"),
        "verification": ("openai:gpt-5.6-luna", "high"),
    }
