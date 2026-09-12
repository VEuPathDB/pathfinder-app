"""The saved conversation state, rebuilt by the build that resumes it."""

from __future__ import annotations

from pydantic import ValidationError

from pathfinder.ai.graph.state import PipelineState
from pathfinder.platform.errors import ConversationFromEarlierBuildError


def rebuilt_state(state: PipelineState) -> PipelineState:
    """Every record of the state as this build's model, or a plain refusal.

    The checkpoint serializer hands back a state it could not validate with
    its nested records left as mappings; validating the dump rebuilds them,
    drops the fields this build no longer declares, and refuses the rest.
    """
    try:
        return PipelineState.model_validate(state.model_dump())
    except ValidationError as exc:
        reasons = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()[:3]
        )
        raise ConversationFromEarlierBuildError(
            str(state.conversation_id), reasons
        ) from exc
