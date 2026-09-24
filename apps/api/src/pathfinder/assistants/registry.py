"""The composition root: which assistants this deployment serves."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from assistant_core.platform.types import ModelProvider, TierName
from assistant_core.registry import AssistantRegistry

from pathfinder.ai.agents.registry import phase_defaults
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.assistants.site_help.agent import SITE_HELP_MODEL
from pathfinder.assistants.site_help.spec import build_site_help_spec
from pathfinder.platform.config import get_settings
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


def _compile_time_models() -> dict[str, dict[str, str]]:
    """Each installed assistant's roles and the model each role bakes in."""
    return {
        PATHFINDER_ASSISTANT_ID: phase_defaults(),
        SITE_HELP_ASSISTANT_ID: {SITE_HELP_ASSISTANT_ID: SITE_HELP_MODEL},
    }


def _defaults_of(
    assistant_id: str, provider: ModelProvider, tier: TierName
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for role, baked_in in _compile_time_models()[assistant_id].items():
        config = resolve_phase_tier_config(assistant_id, provider, tier, role)
        resolved[role] = baked_in if config is None else config.model_id
    return resolved


def installed_phase_defaults(provider: ModelProvider, tier: TierName) -> dict[str, str]:
    """The model every role of every installed assistant runs on when the user
    pins nothing: the model ``tier`` gives the role on ``provider``, and the
    role's compile-time model where the tier names no config for it.
    """
    resolved: dict[str, str] = {}
    for assistant_id in _compile_time_models():
        resolved.update(_defaults_of(assistant_id, provider, tier))
    return resolved


def assistant_role_models(
    assistant_id: str, picks: Mapping[str, str]
) -> dict[str, str]:
    """The model each role of one assistant runs this turn: the pick, else the
    deployment's default for that role."""
    settings = get_settings()
    defaults = _defaults_of(
        assistant_id, settings.default_provider, settings.default_tier
    )
    return {role: picks.get(role) or default for role, default in defaults.items()}


__all__ = [
    "assistant_role_models",
    "get_assistant_registry",
    "installed_phase_defaults",
]
