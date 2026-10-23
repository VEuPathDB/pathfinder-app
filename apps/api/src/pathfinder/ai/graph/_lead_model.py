"""Which model the Lead runs under for one turn.

The mock provider swaps the whole model; otherwise the per-request override
wins over the configured tier, which wins over the agent's baked model.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass

from assistant_core.models.capture import maybe_wrap_model
from assistant_core.models.settings import baked_model_id, build_model_settings
from assistant_core.platform.types import ReasoningEffort

from pathfinder.ai.lead.lead_agent import LeadAgent
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.model_keys import is_mock_deployment, keyed_model
from pathfinder.platform.tiers import deployment_role_config, tier_model

_LEAD_ROLE = "lead"


@dataclass(frozen=True)
class LeadModelContext:
    """What one Lead turn runs as: the agent override, the model it resolves
    to, and the reasoning effort that model runs at."""

    override: AbstractContextManager[None]
    model_id: str
    reasoning_effort: ReasoningEffort | None


def resolve_lead_model_context(
    agent: LeadAgent,
    *,
    model_override: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
) -> LeadModelContext:
    """The agent override to run under, the model id it resolves to, and the
    effort it runs at."""
    if is_mock_deployment():
        return LeadModelContext(
            override=agent.override(model=get_mock_model()),
            model_id="mock:lead",
            reasoning_effort=None,
        )

    settings = get_settings()
    tier_cfg = deployment_role_config(PATHFINDER_ASSISTANT_ID, _LEAD_ROLE)
    effective_model = model_override or tier_model(
        PATHFINDER_ASSISTANT_ID,
        settings.default_provider,
        settings.default_tier,
        _LEAD_ROLE,
        compile_time=baked_model_id(agent),
    )
    effort = reasoning_effort or (
        tier_cfg.reasoning_effort if tier_cfg is not None else None
    )
    return LeadModelContext(
        override=agent.override(
            model=maybe_wrap_model(keyed_model(effective_model), _LEAD_ROLE),
            model_settings=build_model_settings(effective_model, thinking=effort),
        ),
        model_id=effective_model,
        reasoning_effort=effort,
    )


__all__ = ["LeadModelContext", "resolve_lead_model_context"]
