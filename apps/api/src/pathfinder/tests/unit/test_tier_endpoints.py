"""Structural assertions for the tiers endpoint and tier preset registry.

These tests refuse to settle for "key exists" — every assertion pins an
exact value, an exact key set, or a behavioral invariant that catches
silent regressions (model removed from catalog, reasoning_effort downgraded
to a non-reasoning model, phase added or dropped).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.ai.models.catalog import get_model_entry
from pathfinder.ai.models.tiers import TIER_PRESETS, PhaseTierConfig, TierPreset
from pathfinder.transport.http.routers.tiers import TierListResponse, list_tiers

EXPECTED_PROVIDERS: frozenset[str] = frozenset({"anthropic", "openai", "google"})
EXPECTED_TIERS: frozenset[str] = frozenset({"default", "quality", "balanced", "fast"})
EXPECTED_PHASES: tuple[str, ...] = (
    "lead",
    "frame",
    "execution",
    "verification",
)
VALID_REASONING_EFFORTS: frozenset[str] = frozenset({"low", "medium", "high"})


def _phase_cfg(preset: TierPreset, phase: str) -> PhaseTierConfig:
    cfg = preset.for_role(phase)
    assert cfg is not None, f"preset does not cover phase {phase!r}"
    return cfg


async def _list_tiers() -> TierListResponse:
    return await list_tiers()


async def test_endpoint_returns_exactly_expected_provider_set() -> None:
    response = await _list_tiers()
    assert set(response.presets.keys()) == EXPECTED_PROVIDERS


async def test_endpoint_returns_exactly_expected_tier_names_per_provider() -> None:
    response = await _list_tiers()
    for provider, tiers in response.presets.items():
        assert set(tiers.keys()) == EXPECTED_TIERS, (
            f"{provider}: tier names were {sorted(tiers.keys())!r}, "
            f"expected {sorted(EXPECTED_TIERS)!r}"
        )


async def test_endpoint_response_matches_in_process_tier_registry() -> None:
    """Endpoint output equals the canonical registry — no transformation drift."""
    response = await _list_tiers()
    expected = TierListResponse(presets=TIER_PRESETS)
    assert response == expected


async def test_each_preset_covers_exactly_the_runtime_phases() -> None:
    response = await _list_tiers()
    expected_phase_set = set(EXPECTED_PHASES)
    for provider, tiers in response.presets.items():
        for tier_name, preset in tiers.items():
            phases = preset.model_dump(by_alias=False)
            assert set(phases.keys()) == expected_phase_set, (
                f"{provider}/{tier_name}: phases were "
                f"{sorted(phases.keys())!r}, expected {sorted(expected_phase_set)!r}"
            )


async def test_every_phase_config_is_well_typed() -> None:
    response = await _list_tiers()
    for provider, tiers in response.presets.items():
        for tier_name, preset in tiers.items():
            for phase in EXPECTED_PHASES:
                cfg = _phase_cfg(preset, phase)
                assert type(cfg) is PhaseTierConfig
                head, _, tail = cfg.model_id.partition(":")
                assert head == provider, (
                    f"{provider}/{tier_name}/{phase}: model_id "
                    f"{cfg.model_id!r} prefix {head!r} != provider {provider!r}"
                )
                assert tail, (
                    f"{provider}/{tier_name}/{phase}: model_id "
                    f"{cfg.model_id!r} has empty model name after ':'"
                )
                assert cfg.reasoning_effort in VALID_REASONING_EFFORTS, (
                    f"{provider}/{tier_name}/{phase}: "
                    f"reasoning_effort {cfg.reasoning_effort!r} not in "
                    f"{sorted(VALID_REASONING_EFFORTS)!r}"
                )


async def test_every_preset_model_id_resolves_in_catalog() -> None:
    for provider, tiers in TIER_PRESETS.items():
        for tier_name, preset in tiers.items():
            for phase in EXPECTED_PHASES:
                cfg = _phase_cfg(preset, phase)
                entry = get_model_entry(cfg.model_id)
                assert entry is not None, (
                    f"{provider}/{tier_name}/{phase}: {cfg.model_id} not in catalog"
                )
                assert entry.id == cfg.model_id
                assert entry.provider == provider, (
                    f"{cfg.model_id} resolved to provider {entry.provider!r} "
                    f"but is wired into preset for {provider!r}"
                )
                assert entry.context_size > 0, (
                    f"{cfg.model_id} has context_size=0; tier presets must "
                    "point at production-ready models"
                )
                assert entry.name, f"{cfg.model_id} has empty display name"


async def test_high_reasoning_effort_only_targets_reasoning_models() -> None:
    """A tier asking for 'high' effort against a non-reasoning model is a
    silent waste — the provider downgrades transparently and the user pays
    for capability they cannot use.
    """
    for provider, tiers in TIER_PRESETS.items():
        for tier_name, preset in tiers.items():
            for phase in EXPECTED_PHASES:
                cfg = _phase_cfg(preset, phase)
                if cfg.reasoning_effort != "high":
                    continue
                entry = get_model_entry(cfg.model_id)
                assert entry is not None
                assert entry.supports_reasoning is True, (
                    f"{provider}/{tier_name}/{phase}: {cfg.model_id} "
                    "is configured for reasoning_effort=high but "
                    "supports_reasoning=False"
                )


async def test_quality_tier_lead_uses_a_reasoning_model_per_provider() -> None:
    """Lead drives the whole turn; on the 'quality' tier every provider must
    wire a reasoning-capable model into it.
    """
    for provider, tiers in TIER_PRESETS.items():
        cfg = tiers["quality"].lead
        entry = get_model_entry(cfg.model_id)
        assert entry is not None
        assert entry.supports_reasoning is True, (
            f"{provider}/quality/lead: {cfg.model_id} is not a reasoning model"
        )


def _assign(target: object, field: str, value: object) -> None:
    """Write one field of a model, whatever the model allows."""
    setattr(target, field, value)


def test_tier_preset_is_frozen() -> None:
    """Mutability would let runtime code reshape presets — pin the immutability."""
    preset = TIER_PRESETS["anthropic"]["quality"]
    assert preset.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        _assign(preset, "lead", preset.execution)


def test_phase_tier_config_is_frozen() -> None:
    cfg = TIER_PRESETS["anthropic"]["quality"].lead
    assert cfg.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        _assign(cfg, "model_id", "openai:gpt-5.6-luna")
