"""The composition root: which assistants this deployment serves."""

from __future__ import annotations

from functools import lru_cache

from assistant_core.platform.types import ModelProvider, TierName
from assistant_core.registry import AssistantRegistry

from pathfinder.ai.agents.registry import phase_defaults
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.assistants.site_help.agent import SITE_HELP_MODEL
from pathfinder.assistants.site_help.spec import build_site_help_spec
from pathfinder.platform.identity import (
    PATHFINDER_ASSISTANT_ID,
    SITE_HELP_ASSISTANT_ID,
)
from pathfinder.platform.tiers import resolve_phase_tier_config


@lru_cache(maxsize=1)
def get_assistant_registry() -> AssistantRegistry:
    """Every installed assistant. Built once; the specs hold no per-turn state."""
    return AssistantRegistry(
        specs=[build_pathfinder_spec(), build_site_help_spec()],
        default_id=PATHFINDER_ASSISTANT_ID,
    )


def installed_phase_defaults(provider: ModelProvider, tier: TierName) -> dict[str, str]:
    """The model every role of every installed assistant runs on when the user
    pins nothing: the model ``tier`` gives the role on ``provider``, and the
    role's compile-time model where the tier names no config for it.
    """
    compile_time: tuple[tuple[str, dict[str, str]], ...] = (
        (PATHFINDER_ASSISTANT_ID, phase_defaults()),
        (SITE_HELP_ASSISTANT_ID, {SITE_HELP_ASSISTANT_ID: SITE_HELP_MODEL}),
    )
    resolved: dict[str, str] = {}
    for assistant_id, roles in compile_time:
        for role, baked_in in roles.items():
            config = resolve_phase_tier_config(assistant_id, provider, tier, role)
            resolved[role] = baked_in if config is None else config.model_id
    return resolved


__all__ = ["get_assistant_registry", "installed_phase_defaults"]
