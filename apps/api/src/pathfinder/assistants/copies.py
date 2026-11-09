from __future__ import annotations

from assistant_core.conversation.serde import build_checkpoint_serde

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.persistence.repositories.checkpoint_rows import ChannelRewrite
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


def _domain(value: object) -> object:
    return StrategyDomainState.model_validate(value).for_another_account()


def _no_memories(_value: object) -> object:
    return []


def copy_rewrite(assistant_id: str) -> ChannelRewrite | None:
    """How a copy into another account rewrites the assistant's saved state."""
    if assistant_id != PATHFINDER_ASSISTANT_ID:
        return None
    return ChannelRewrite(
        serde=build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES),
        channels={"domain": _domain, "retrieved_memories": _no_memories},
    )
