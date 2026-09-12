"""Tier preset registry - maps (assistant, provider, tier) to per-role configs.

Each cloud provider defines tiers that auto-populate an assistant's roles with
a model and a reasoning effort. The frontend fetches these via
``GET /api/v1/tiers`` so it never hardcodes model assignments, and each agent
applies the configured tier beneath an explicit per-role user pick.

A preset names the roles of the assistant it belongs to; a role a preset omits
falls back to that agent's compile-time model.
"""

from dataclasses import dataclass

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider, ReasoningEffort, TierName
from pydantic import ConfigDict

from pathfinder.platform.identity import (
    PATHFINDER_ASSISTANT_ID,
    SITE_HELP_ASSISTANT_ID,
)

__all__ = [
    "KNOWN_ROLES",
    "TIER_PRESETS",
    "PhaseTierConfig",
    "TierPreset",
    "get_tier_preset",
    "resolve_phase_tier_config",
]


class PhaseTierConfig(CamelModel):
    """Model + reasoning effort for a single role."""

    model_config = ConfigDict(frozen=True, protected_namespaces=())

    model_id: str
    reasoning_effort: ReasoningEffort


class TierPreset(CamelModel):
    """One assistant's roles, each with the model and effort this tier runs it on."""

    model_config = ConfigDict(frozen=True)

    roles: dict[str, PhaseTierConfig]

    def for_role(self, role: str) -> PhaseTierConfig | None:
        """The config this preset carries for ``role``, or ``None`` when the
        preset does not cover it."""
        return self.roles.get(role)


@dataclass(frozen=True)
class _Tier:
    """The two models one tier runs: the one that reasons, and the cheaper one."""

    thinker: PhaseTierConfig
    worker: PhaseTierConfig


def _split(
    reasoning_model: str,
    reasoning_effort: ReasoningEffort,
    execution_model: str,
    execution_effort: ReasoningEffort,
) -> _Tier:
    return _Tier(
        thinker=PhaseTierConfig(
            model_id=reasoning_model, reasoning_effort=reasoning_effort
        ),
        worker=PhaseTierConfig(
            model_id=execution_model, reasoning_effort=execution_effort
        ),
    )


def _uniform(model_id: str, effort: ReasoningEffort) -> _Tier:
    """A tier that runs every role on one model at one effort."""
    cfg = PhaseTierConfig(model_id=model_id, reasoning_effort=effort)
    return _Tier(thinker=cfg, worker=cfg)


_OPENAI: dict[TierName, _Tier] = {
    "quality": _split("openai:gpt-5.6-sol", "high", "openai:gpt-5.6-terra", "medium"),
    "balanced": _split(
        "openai:gpt-5.6-terra", "medium", "openai:gpt-5.6-luna", "medium"
    ),
    "default": _uniform("openai:gpt-5.6-luna", "medium"),
    "fast": _uniform("openai:gpt-5.6-luna", "low"),
}

_ANTHROPIC: dict[TierName, _Tier] = {
    "quality": _split(
        "anthropic:claude-opus-5", "high", "anthropic:claude-sonnet-5", "medium"
    ),
    "balanced": _split(
        "anthropic:claude-sonnet-5", "medium", "anthropic:claude-haiku-4-5", "medium"
    ),
    "default": _uniform("anthropic:claude-sonnet-5", "medium"),
    "fast": _uniform("anthropic:claude-haiku-4-5", "low"),
}

_GOOGLE: dict[TierName, _Tier] = {
    "quality": _split(
        "google:gemini-3.1-pro-preview", "high", "google:gemini-3.6-flash", "medium"
    ),
    "balanced": _split(
        "google:gemini-3.6-flash", "medium", "google:gemini-3.5-flash-lite", "medium"
    ),
    "default": _uniform("google:gemini-3.6-flash", "medium"),
    "fast": _uniform("google:gemini-3.5-flash-lite", "low"),
}

_BY_PROVIDER: dict[ModelProvider, dict[TierName, _Tier]] = {
    "openai": _OPENAI,
    "anthropic": _ANTHROPIC,
    "google": _GOOGLE,
}


def _pathfinder_preset(tier: _Tier) -> TierPreset:
    """Spend on the roles that reason, and run the mechanical WDK
    step-building role on the cheaper model."""
    return TierPreset(
        roles={
            "lead": tier.thinker,
            "frame": tier.thinker,
            "execution": tier.worker,
            "verification": tier.thinker,
        },
    )


def _site_help_preset(tier: _Tier) -> TierPreset:
    """Site help is one agent that reports what the catalog holds, so its one
    role takes the cheaper model. A one-agent assistant names its role after
    itself."""
    return TierPreset(roles={SITE_HELP_ASSISTANT_ID: tier.worker})


TIER_PRESETS: dict[str, dict[ModelProvider, dict[TierName, TierPreset]]] = {
    assistant_id: {
        provider: {name: build(tier) for name, tier in tiers.items()}
        for provider, tiers in _BY_PROVIDER.items()
    }
    for assistant_id, build in (
        (PATHFINDER_ASSISTANT_ID, _pathfinder_preset),
        (SITE_HELP_ASSISTANT_ID, _site_help_preset),
    )
}

# Every role any installed assistant runs a model for. A request that pins a
# model for a role outside this set is refused at the chat boundary.
KNOWN_ROLES: frozenset[str] = frozenset(
    role
    for by_provider in TIER_PRESETS.values()
    for by_tier in by_provider.values()
    for preset in by_tier.values()
    for role in preset.roles
)


def get_tier_preset(
    assistant_id: str,
    provider: ModelProvider,
    tier: TierName,
) -> TierPreset | None:
    """The preset for ``(assistant_id, provider, tier)``, or ``None`` when
    unconfigured.

    ``custom`` is deliberately unconfigured: it means the user pinned models
    per role, so there is no preset to apply.
    """
    return TIER_PRESETS.get(assistant_id, {}).get(provider, {}).get(tier)


def resolve_phase_tier_config(
    assistant_id: str,
    provider: ModelProvider,
    tier: TierName,
    role: str,
) -> PhaseTierConfig | None:
    """The configured model + effort for one role, or ``None`` when the tier
    does not cover this assistant, this provider or this role (caller falls
    back to the agent's own model)."""
    preset = get_tier_preset(assistant_id, provider, tier)
    if preset is None:
        return None
    return preset.for_role(role)
