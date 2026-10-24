"""The composition root: which assistants this deployment serves."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache

from assistant_core.platform.types import ModelProvider, TierName
from assistant_core.registry import AssistantRegistry
from assistant_core.spec import AssistantSpec

from pathfinder.ai.agents.registry import phase_defaults
from pathfinder.ai.audit.auditor import audit_compile_time_models
from pathfinder.assistants.audit.spec import build_audit_spec
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID, PATHFINDER_ASSISTANT_ID
from pathfinder.platform.tiers import AUDITOR_ROLE, tier_model


@dataclass(frozen=True, kw_only=True)
class InstalledAssistant:
    build_spec: Callable[[], AssistantSpec]
    compile_time_models: Callable[[], dict[str, str]]
    prompt_role: str
    turn_roles: frozenset[str]


def installed_assistants() -> dict[str, InstalledAssistant]:
    return {
        PATHFINDER_ASSISTANT_ID: InstalledAssistant(
            build_spec=build_pathfinder_spec,
            compile_time_models=phase_defaults,
            prompt_role="lead",
            turn_roles=frozenset(phase_defaults()),
        ),
        AUDIT_ASSISTANT_ID: InstalledAssistant(
            build_spec=build_audit_spec,
            compile_time_models=audit_compile_time_models,
            prompt_role=AUDITOR_ROLE,
            turn_roles=frozenset({AUDITOR_ROLE}),
        ),
    }


@lru_cache(maxsize=1)
def get_assistant_registry() -> AssistantRegistry:
    """Every installed assistant. Built once; the specs hold no per-turn state."""
    return AssistantRegistry(
        specs=[one.build_spec() for one in installed_assistants().values()],
        default_id=PATHFINDER_ASSISTANT_ID,
    )


def _defaults_of(
    assistant_id: str, provider: ModelProvider, tier: TierName
) -> dict[str, str]:
    models = installed_assistants()[assistant_id].compile_time_models()
    return {
        role: tier_model(assistant_id, provider, tier, role, compile_time=baked_in)
        for role, baked_in in models.items()
    }


def installed_phase_defaults(provider: ModelProvider, tier: TierName) -> dict[str, str]:
    """The model every role of every installed assistant runs on when the user
    pins nothing: the model ``tier`` gives the role on ``provider``, and the
    role's compile-time model where the tier names no config for it.
    """
    resolved: dict[str, str] = {}
    for assistant_id in installed_assistants():
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


def turn_role_models(assistant_id: str, picks: Mapping[str, str]) -> dict[str, str]:
    """The model of each role a chat turn of one assistant runs."""
    runs = installed_assistants()[assistant_id].turn_roles
    models = assistant_role_models(assistant_id, picks)
    return {role: model for role, model in models.items() if role in runs}


def turn_trace_labels(assistant_id: str, picks: Mapping[str, str]) -> dict[str, str]:
    """The provider, the tier and each role's model, as one turn's trace labels."""
    settings = get_settings()
    models = assistant_role_models(assistant_id, picks)
    return {
        "provider": settings.default_provider,
        "tier": settings.default_tier,
        **{f"model_{role}": model for role, model in models.items()},
    }


def prompt_reader_model(assistant_id: str, picks: Mapping[str, str]) -> str:
    """The model that reads the user's message this turn."""
    role = installed_assistants()[assistant_id].prompt_role
    return assistant_role_models(assistant_id, picks)[role]


__all__ = [
    "InstalledAssistant",
    "assistant_role_models",
    "get_assistant_registry",
    "installed_assistants",
    "installed_phase_defaults",
    "prompt_reader_model",
    "turn_role_models",
    "turn_trace_labels",
]
