from __future__ import annotations

from assistant_core.models.capture import maybe_wrap_model
from assistant_core.models.settings import build_model_settings
from assistant_core.platform.types import ReasoningEffort

from pathfinder.ai.explore.explore_agent import EXPLORE_MODEL, ExploreAgent
from pathfinder.ai.graph._lead_model import LeadModelContext
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.model_keys import is_mock_deployment, keyed_model
from pathfinder.platform.tiers import EXPLORE_ROLE, deployment_role_config, tier_model


def resolve_explore_model_context(
    agent: ExploreAgent,
    *,
    model_override: str | None,
    reasoning_effort: ReasoningEffort | None,
) -> LeadModelContext:
    if is_mock_deployment():
        return LeadModelContext(
            override=agent.override(model=get_mock_model()),
            model_id="mock:explore",
            reasoning_effort=None,
        )
    settings = get_settings()
    tier_cfg = deployment_role_config(PATHFINDER_ASSISTANT_ID, EXPLORE_ROLE)
    model_id = model_override or tier_model(
        PATHFINDER_ASSISTANT_ID,
        settings.default_provider,
        settings.default_tier,
        EXPLORE_ROLE,
        compile_time=EXPLORE_MODEL,
    )
    effort = reasoning_effort or (
        tier_cfg.reasoning_effort if tier_cfg is not None else None
    )
    return LeadModelContext(
        override=agent.override(
            model=maybe_wrap_model(keyed_model(model_id), EXPLORE_ROLE),
            model_settings=build_model_settings(model_id, thinking=effort),
        ),
        model_id=model_id,
        reasoning_effort=effort,
    )
