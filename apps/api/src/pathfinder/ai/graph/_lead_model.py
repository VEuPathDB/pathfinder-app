"""Which model the Lead runs under for one turn.

The mock provider swaps the whole model; otherwise the per-request override
wins over the configured tier, which wins over the agent's baked model.
"""

from __future__ import annotations

from typing import Any

from assistant_core.models.capture import maybe_wrap_model
from assistant_core.models.settings import baked_model_id, build_model_settings
from assistant_core.platform.types import ReasoningEffort

from pathfinder.ai.lead.lead_agent import LeadAgent
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.tiers import resolve_phase_tier_config

_LEAD_ROLE = "lead"


def resolve_lead_model_context(
    agent: LeadAgent,
    *,
    model_override: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
) -> tuple[Any, str]:
    """The agent override to run under, and the model id it resolves to."""
    if get_settings().pathfinder_chat_provider.strip().lower() == "mock":
        return agent.override(model=get_mock_model()), "mock:lead"

    settings = get_settings()
    tier_cfg = resolve_phase_tier_config(
        PATHFINDER_ASSISTANT_ID,
        settings.default_provider,
        settings.default_tier,
        _LEAD_ROLE,
    )
    tier_model = tier_cfg.model_id if tier_cfg is not None else None
    effective_model = model_override or tier_model or baked_model_id(agent)
    effort = reasoning_effort or (
        tier_cfg.reasoning_effort if tier_cfg is not None else None
    )
    return (
        agent.override(
            model=maybe_wrap_model(effective_model, _LEAD_ROLE),
            model_settings=build_model_settings(effective_model, thinking=effort),
        ),
        effective_model,
    )


__all__ = ["resolve_lead_model_context"]
