"""The seam between the runtime's per-role model selection and PathFinder's roles.

The runtime routes a model choice per role. The role NAMES are the product's
vocabulary, so a core surface that spells them out cannot serve a second
assistant. The product declares them once in ``ai.agents.roles`` and the HTTP
boundary validates against that declaration.
"""

from __future__ import annotations

from types import ModuleType
from typing import get_type_hints
from uuid import uuid4

import assistant_core.graph.turn_state as turn_state_mod
import pytest
from assistant_core.graph.runtime import TurnContext
from assistant_core.graph.turn_state import (
    PendingApproval,
    SubAgentApprovalPending,
)
from assistant_core.platform.types import ReasoningEffort
from pydantic import ValidationError

import pathfinder.ai.agents.registry as registry_mod
import pathfinder.ai.conversation._turn_helpers as turn_helpers_mod
import pathfinder.ai.graph.runtime as runtime_mod
import pathfinder.ai.models.tiers as tiers_mod
from pathfinder.ai.agents.registry import phase_defaults
from pathfinder.ai.agents.roles import PHASE_ROLES
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.models.tiers import (
    TIER_PRESETS,
    TierPreset,
    resolve_phase_tier_config,
)

CORE_MODULES: tuple[ModuleType, ...] = (
    runtime_mod,
    turn_state_mod,
    tiers_mod,
    registry_mod,
    turn_helpers_mod,
)

ROLE_NAMES: frozenset[str] = frozenset({"lead", "frame", "execution", "verification"})


@pytest.mark.parametrize("module", CORE_MODULES, ids=lambda m: m.__name__)
def test_core_module_does_not_bind_the_product_role_literal(
    module: ModuleType,
) -> None:
    assert "PhaseRole" not in vars(module)
    assert "PHASE_ROLES" not in vars(module)


def test_turn_context_keys_its_model_selection_by_plain_string() -> None:
    hints = get_type_hints(TurnContext)
    assert hints["phase_models"] == dict[str, str]
    assert hints["phase_reasoning"] == dict[str, ReasoningEffort]


def test_pending_approval_names_its_phase_with_a_plain_string() -> None:
    assert PendingApproval.model_fields["phase"].annotation is str
    assert SubAgentApprovalPending.model_fields["role"].annotation is str


def test_tier_resolution_takes_a_plain_string_role() -> None:
    assert get_type_hints(resolve_phase_tier_config)["role"] is str
    assert get_type_hints(TierPreset.for_role)["role"] is str


def test_tier_preset_owns_the_mapping_from_role_to_config() -> None:
    preset = TIER_PRESETS["openai"]["quality"]
    assert preset.for_role("lead") == preset.lead
    assert preset.for_role("execution") == preset.execution
    assert preset.for_role("planner") is None


def test_every_declared_role_still_resolves_a_tier_config() -> None:
    models = [
        cfg.model_id
        for role in PHASE_ROLES
        if (cfg := resolve_phase_tier_config("openai", "quality", role)) is not None
    ]
    assert len(models) == len(PHASE_ROLES)
    assert "" not in models


def test_registry_still_reports_a_default_model_for_every_declared_role() -> None:
    defaults = phase_defaults()
    assert set(defaults) == ROLE_NAMES
    assert all(model_id for model_id in defaults.values())


def test_request_boundary_still_refuses_an_undeclared_role_the_same_way() -> None:
    with pytest.raises(ValidationError) as exc:
        ChatRequestBody.model_validate(
            {
                "conversationId": str(uuid4()),
                "phaseModels": {"planner": "openai:gpt-5.6-luna"},
            },
        )
    errors = exc.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "literal_error"
    assert errors[0]["loc"] == ("phaseModels", "planner", "[key]")


def test_request_boundary_accepts_every_declared_role() -> None:
    body = ChatRequestBody.model_validate(
        {
            "conversationId": str(uuid4()),
            "phaseModels": dict.fromkeys(PHASE_ROLES, "openai:gpt-5.6-luna"),
            "phaseReasoning": dict.fromkeys(PHASE_ROLES, "medium"),
        },
    )
    assert set(body.phase_models) == ROLE_NAMES
    assert set(body.phase_reasoning) == ROLE_NAMES
