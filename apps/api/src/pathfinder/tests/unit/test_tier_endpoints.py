"""Structural assertions for the tiers endpoint and tier preset registry.

These tests refuse to settle for "key exists" - every assertion pins an
exact value, an exact key set, or a behavioral invariant that catches
silent regressions (model removed from catalog, reasoning_effort downgraded
to a non-reasoning model, role added or dropped).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from pathfinder.ai.models.catalog import get_model_entry
from pathfinder.platform.identity import (
    PATHFINDER_ASSISTANT_ID,
    SITE_HELP_ASSISTANT_ID,
)
from pathfinder.platform.tiers import TIER_PRESETS, PhaseTierConfig
from pathfinder.transport.http.routers.tiers import TierListResponse, list_tiers

EXPECTED_ASSISTANTS: frozenset[str] = frozenset(
    {PATHFINDER_ASSISTANT_ID, SITE_HELP_ASSISTANT_ID},
)
EXPECTED_PROVIDERS: frozenset[str] = frozenset({"anthropic", "openai", "google"})
EXPECTED_TIERS: frozenset[str] = frozenset({"default", "quality", "balanced", "fast"})
EXPECTED_ROLES: dict[str, frozenset[str]] = {
    PATHFINDER_ASSISTANT_ID: frozenset({"lead", "frame", "execution", "verification"}),
    SITE_HELP_ASSISTANT_ID: frozenset({SITE_HELP_ASSISTANT_ID}),
}
VALID_REASONING_EFFORTS: frozenset[str] = frozenset({"low", "medium", "high"})


def _every_config() -> Iterator[tuple[str, str, str, str, PhaseTierConfig]]:
    """Every (assistant, provider, tier, role) the registry configures."""
    for assistant_id, by_provider in TIER_PRESETS.items():
        for provider, by_tier in by_provider.items():
            for tier_name, preset in by_tier.items():
                for role, cfg in preset.roles.items():
                    yield assistant_id, provider, tier_name, role, cfg


def _quality_lead() -> Iterator[tuple[str, PhaseTierConfig]]:
    """The lead config of every provider's quality tier."""
    for provider, by_tier in TIER_PRESETS[PATHFINDER_ASSISTANT_ID].items():
        cfg = by_tier["quality"].for_role("lead")
        assert cfg is not None
        yield provider, cfg


async def _list_tiers() -> TierListResponse:
    return await list_tiers()


async def test_endpoint_returns_exactly_expected_assistant_set() -> None:
    response = await _list_tiers()
    assert set(response.presets.keys()) == EXPECTED_ASSISTANTS


async def test_endpoint_returns_exactly_expected_provider_set() -> None:
    response = await _list_tiers()
    for assistant_id, by_provider in response.presets.items():
        assert set(by_provider.keys()) == EXPECTED_PROVIDERS, assistant_id


async def test_endpoint_returns_exactly_expected_tier_names_per_provider() -> None:
    response = await _list_tiers()
    for assistant_id, by_provider in response.presets.items():
        for provider, tiers in by_provider.items():
            assert set(tiers.keys()) == EXPECTED_TIERS, (
                f"{assistant_id}/{provider}: tier names were "
                f"{sorted(tiers.keys())!r}, expected {sorted(EXPECTED_TIERS)!r}"
            )


async def test_endpoint_response_matches_in_process_tier_registry() -> None:
    """Endpoint output equals the canonical registry - no transformation drift."""
    response = await _list_tiers()
    expected = TierListResponse(presets=TIER_PRESETS)
    assert response == expected


async def test_each_preset_names_the_roles_of_its_own_assistant() -> None:
    response = await _list_tiers()
    for assistant_id, by_provider in response.presets.items():
        for provider, tiers in by_provider.items():
            for tier_name, preset in tiers.items():
                assert set(preset.roles) == EXPECTED_ROLES[assistant_id], (
                    f"{assistant_id}/{provider}/{tier_name}: roles were "
                    f"{sorted(preset.roles)!r}"
                )


def test_every_role_config_is_well_typed() -> None:
    for assistant_id, provider, tier_name, role, cfg in _every_config():
        where = f"{assistant_id}/{provider}/{tier_name}/{role}"
        assert type(cfg) is PhaseTierConfig
        head, _, tail = cfg.model_id.partition(":")
        assert head == provider, (
            f"{where}: model_id {cfg.model_id!r} prefix {head!r} != {provider!r}"
        )
        assert tail, f"{where}: model_id {cfg.model_id!r} has no model name after ':'"
        assert cfg.reasoning_effort in VALID_REASONING_EFFORTS, (
            f"{where}: reasoning_effort {cfg.reasoning_effort!r} not in "
            f"{sorted(VALID_REASONING_EFFORTS)!r}"
        )


def test_every_preset_model_id_resolves_in_catalog() -> None:
    for assistant_id, provider, tier_name, role, cfg in _every_config():
        where = f"{assistant_id}/{provider}/{tier_name}/{role}"
        entry = get_model_entry(cfg.model_id)
        assert entry is not None, f"{where}: {cfg.model_id} not in catalog"
        assert entry.id == cfg.model_id
        assert entry.provider == provider, (
            f"{cfg.model_id} resolved to provider {entry.provider!r} "
            f"but is wired into a preset for {provider!r}"
        )
        assert entry.context_size > 0, (
            f"{cfg.model_id} has context_size=0; tier presets must "
            "point at production-ready models"
        )
        assert entry.name, f"{cfg.model_id} has empty display name"


def test_high_reasoning_effort_only_targets_reasoning_models() -> None:
    """A tier asking for 'high' effort against a non-reasoning model is a
    silent waste - the provider downgrades transparently and the user pays
    for capability they cannot use.
    """
    for assistant_id, provider, tier_name, role, cfg in _every_config():
        if cfg.reasoning_effort != "high":
            continue
        entry = get_model_entry(cfg.model_id)
        assert entry is not None
        assert entry.supports_reasoning is True, (
            f"{assistant_id}/{provider}/{tier_name}/{role}: {cfg.model_id} "
            "is configured for reasoning_effort=high but supports_reasoning=False"
        )


def test_quality_tier_lead_uses_a_reasoning_model_per_provider() -> None:
    """Lead drives the whole turn; on the 'quality' tier every provider must
    wire a reasoning-capable model into it.
    """
    for provider, cfg in _quality_lead():
        entry = get_model_entry(cfg.model_id)
        assert entry is not None
        assert entry.supports_reasoning is True, (
            f"{provider}/quality/lead: {cfg.model_id} is not a reasoning model"
        )


def _assign(target: object, field: str, value: object) -> None:
    """Write one field of a model, whatever the model allows."""
    setattr(target, field, value)


def test_tier_preset_is_frozen() -> None:
    """Mutability would let runtime code reshape presets - pin the immutability."""
    preset = TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["anthropic"]["quality"]
    assert preset.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        _assign(preset, "roles", {})


def test_phase_tier_config_is_frozen() -> None:
    cfg = TIER_PRESETS[PATHFINDER_ASSISTANT_ID]["anthropic"]["quality"].roles["lead"]
    assert cfg.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        _assign(cfg, "model_id", "openai:gpt-5.6-luna")
