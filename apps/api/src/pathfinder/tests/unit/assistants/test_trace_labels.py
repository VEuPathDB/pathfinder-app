"""A turn's trace names the tier and the model each role runs on."""

from __future__ import annotations

from pathfinder.assistants.registry import assistant_role_models, turn_trace_labels
from pathfinder.platform.config import get_settings


def test_the_labels_carry_the_tier_and_each_role_s_model() -> None:
    picks = {"lead": "openai:picked-for-this-turn"}

    labels = turn_trace_labels("pathfinder", picks)

    settings = get_settings()
    roles = assistant_role_models("pathfinder", picks)
    assert labels == {
        "provider": settings.default_provider,
        "tier": settings.default_tier,
        **{f"model_{role}": model for role, model in roles.items()},
    }
    assert labels["model_lead"] == "openai:picked-for-this-turn"
