"""Tier preset registry - maps (assistant, provider, tier) to per-role configs.

Each cloud provider's tiers are derived from the ranks of its catalog entries,
and auto-populate an assistant's roles with a model and a reasoning effort. The frontend fetches these via
``GET /api/v1/tiers`` so it never hardcodes model assignments, and each agent
applies the configured tier beneath an explicit per-role user pick.

A preset names the roles of the assistant it belongs to; a role a preset omits
falls back to that agent's compile-time model.
"""

from dataclasses import dataclass
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider, ReasoningEffort, TierName
from pydantic import ConfigDict

from pathfinder.domain.provider_keys import KEYABLE_PROVIDERS
from pathfinder.platform.identity import (
    PATHFINDER_ASSISTANT_ID,
    SITE_HELP_ASSISTANT_ID,
)
from pathfinder.platform.model_catalog import (
    ModelEntry,
    ModelRank,
    get_model_catalog,
    provider_default,
    validate_lineup,
)

__all__ = [
    "KNOWN_ROLES",
    "OWN_KEY_TIER_PRESETS",
    "TIER_PRESETS",
    "PhaseTierConfig",
    "TierPreset",
    "derive_tiers",
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


type _Pick = Literal[ModelRank, "default"]
type _Slot = tuple[_Pick, ReasoningEffort]

_RANKS_DOWN: tuple[ModelRank, ...] = ("flagship", "standard", "small")

# The thinker slot, then the worker slot, of each tier.
_SHAPES: dict[TierName, tuple[_Slot, _Slot]] = {
    "quality": (("flagship", "high"), ("standard", "medium")),
    "balanced": (("standard", "medium"), ("small", "medium")),
    "default": (("default", "medium"), ("default", "medium")),
    "fast": (("small", "low"), ("small", "low")),
}


def _model_at(
    entries: tuple[ModelEntry, ...], provider: ModelProvider, pick: _Pick
) -> str:
    """The provider's entry at ``pick``, or at the next rank down it has.

    A validated lineup holds a small entry, so the search always ends.
    """
    if pick == "default":
        return provider_default(provider, entries).id
    return next(
        entry.id
        for rank in _RANKS_DOWN[_RANKS_DOWN.index(pick) :]
        for entry in entries
        if entry.provider == provider and entry.rank == rank
    )


def derive_tiers(
    entries: tuple[ModelEntry, ...], provider: ModelProvider
) -> dict[TierName, _Tier]:
    """The provider's tiers, read from the ranks of its catalog entries.

    A tier whose two slots land on one model runs it at the thinker's effort.

    :raises ValueError: If the entries break a rule of ``validate_lineup``.
    """
    validate_lineup(entries)
    tiers: dict[TierName, _Tier] = {}
    for name, ((think_pick, think_effort), (work_pick, work_effort)) in _SHAPES.items():
        thinker = PhaseTierConfig(
            model_id=_model_at(entries, provider, think_pick),
            reasoning_effort=think_effort,
        )
        worker_id = _model_at(entries, provider, work_pick)
        worker = (
            thinker
            if worker_id == thinker.model_id
            else PhaseTierConfig(model_id=worker_id, reasoning_effort=work_effort)
        )
        tiers[name] = _Tier(thinker=thinker, worker=worker)
    return tiers


_DEPLOYMENT_PAYS = tuple(e for e in get_model_catalog() if e.deployment_may_pay)

_BY_PROVIDER: dict[ModelProvider, dict[TierName, _Tier]] = {
    provider: derive_tiers(_DEPLOYMENT_PAYS, provider) for provider in KEYABLE_PROVIDERS
}

_OWN_KEY_BY_PROVIDER: dict[ModelProvider, dict[TierName, _Tier]] = {
    provider: derive_tiers(get_model_catalog(), provider)
    for provider in KEYABLE_PROVIDERS
}


# VERIFY holds each claim to the reads of the turn, so it checks at this effort
# in every tier.
_VERIFY_EFFORT: ReasoningEffort = "high"


def _pathfinder_preset(tier: _Tier) -> TierPreset:
    """Spend on the Lead and FRAME, which plan the turn, and run BUILD and
    VERIFY on the cheaper model."""
    return TierPreset(
        roles={
            "lead": tier.thinker,
            "frame": tier.thinker,
            "execution": tier.worker,
            "verification": tier.worker.model_copy(
                update={"reasoning_effort": _VERIFY_EFFORT}
            ),
        },
    )


def _site_help_preset(tier: _Tier) -> TierPreset:
    """Site help is one agent that reports what the catalog holds, so its one
    role takes the cheaper model. A one-agent assistant names its role after
    itself."""
    return TierPreset(roles={SITE_HELP_ASSISTANT_ID: tier.worker})


type _Presets = dict[str, dict[ModelProvider, dict[TierName, TierPreset]]]


def _presets(by_provider: dict[ModelProvider, dict[TierName, _Tier]]) -> _Presets:
    return {
        assistant_id: {
            provider: {name: build(tier) for name, tier in tiers.items()}
            for provider, tiers in by_provider.items()
        }
        for assistant_id, build in (
            (PATHFINDER_ASSISTANT_ID, _pathfinder_preset),
            (SITE_HELP_ASSISTANT_ID, _site_help_preset),
        )
    }


# The presets a turn the deployment pays for runs, and the server's own default.
TIER_PRESETS: _Presets = _presets(_BY_PROVIDER)

# The presets a researcher's own key for the provider runs.
OWN_KEY_TIER_PRESETS: _Presets = _presets(_OWN_KEY_BY_PROVIDER)

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
