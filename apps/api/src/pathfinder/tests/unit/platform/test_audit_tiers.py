from __future__ import annotations

from typing import get_args
from uuid import uuid4

import pytest
from assistant_core.platform.types import ModelProvider, TierName
from pydantic import ValidationError

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.domain.provider_keys import KEYABLE_PROVIDERS
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID, PATHFINDER_ASSISTANT_ID
from pathfinder.platform.tiers import (
    AUDIT_ROLES,
    AUDITOR_ROLE,
    KNOWN_ROLES,
    REVIEW_ROLE,
    resolve_phase_tier_config,
    role_model,
    tier_model,
)
from pathfinder.tests._support.models import DEFAULT_MODEL, OPENAI_STANDARD

_TIERS: tuple[TierName, ...] = tuple(
    tier for tier in get_args(TierName) if tier != "custom"
)
_CASES = [(provider, tier) for provider in KEYABLE_PROVIDERS for tier in _TIERS]


def test_the_audit_assistant_is_named_audit() -> None:
    assert (AUDIT_ASSISTANT_ID, AUDITOR_ROLE, REVIEW_ROLE) == (
        "audit",
        "auditor",
        "audit_review",
    )
    assert frozenset({"auditor", "audit_review"}) == AUDIT_ROLES


@pytest.mark.parametrize(("provider", "tier"), _CASES)
def test_the_auditor_runs_on_the_lead_model_and_the_review_on_the_build_model(
    provider: ModelProvider, tier: TierName
) -> None:
    pairs = {
        role: (
            resolve_phase_tier_config(AUDIT_ASSISTANT_ID, provider, tier, role),
            resolve_phase_tier_config(PATHFINDER_ASSISTANT_ID, provider, tier, peer),
        )
        for role, peer in (("auditor", "lead"), ("audit_review", "execution"))
    }

    assert pairs["auditor"][0] is not None
    assert pairs["auditor"][0] == pairs["auditor"][1]
    assert pairs["audit_review"][0] is not None
    assert pairs["audit_review"][0] == pairs["audit_review"][1]


def test_no_audit_role_is_a_known_role() -> None:
    assert AUDIT_ROLES.isdisjoint(KNOWN_ROLES)
    assert frozenset({"lead", "frame", "execution", "verification"}) == KNOWN_ROLES


@pytest.mark.parametrize("role", sorted(AUDIT_ROLES))
def test_the_request_body_refuses_a_pick_for_an_audit_role(role: str) -> None:
    with pytest.raises(ValidationError, match=rf"unknown phase roles: \['{role}'\]"):
        ChatRequestBody.model_validate(
            {"conversationId": str(uuid4()), "phaseModels": {role: DEFAULT_MODEL}}
        )


def test_a_role_no_tier_names_keeps_its_compile_time_model() -> None:
    assert (
        tier_model(
            AUDIT_ASSISTANT_ID, "openai", "custom", AUDITOR_ROLE, compile_time="x:y"
        )
        == "x:y"
    )
    assert (
        tier_model(
            AUDIT_ASSISTANT_ID, "openai", "balanced", AUDITOR_ROLE, compile_time="x:y"
        )
        == OPENAI_STANDARD
    )


def test_the_auditor_runs_on_the_deployments_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "default_provider", "openai")
    monkeypatch.setattr(settings, "default_tier", "balanced")

    assert role_model(AUDIT_ASSISTANT_ID, AUDITOR_ROLE, compile_time="x:y") == (
        OPENAI_STANDARD
    )
