"""The control sets attached to a conversation, and the check that a call names one."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._saved_here import saved_here
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.services.evidence.control_sets import (
    SavedControls,
    saved_control_sets,
)

ATTACH_A_SET = (
    "Save the researcher's ids with build_control_set, or attach a saved set "
    "the researcher names with use_control_set."
)


def unattached_set(
    control_set_id: str, attached: Sequence[NamedControlSet]
) -> str | None:
    """Why a call may not run on this set, or None when the conversation holds it."""
    if any(held.id == control_set_id for held in attached):
        return None
    held = "; ".join(f"{s.id} ({s.name})" for s in attached) or "none"
    return (
        f"control_set_id {control_set_id!r} names no control set attached to "
        f"this conversation. The attached control sets: {held}."
    )


class ControlSetSummary(CamelModel):
    control_set_id: str
    name: str
    positive_count: int
    negative_count: int
    saved_here: bool = False


def control_set_summary(
    saved: SavedControls, conversation_id: UUID | None
) -> ControlSetSummary:
    """A saved set by its name, id and sizes, marked when this conversation saved it."""
    return ControlSetSummary(
        control_set_id=saved.control_set_id,
        name=saved.name,
        positive_count=len(saved.positive_ids),
        negative_count=len(saved.negative_ids),
        saved_here=saved_here(saved.conversation_id, conversation_id),
    )


def listed_control_sets[DepsT](
    ctx: RunContext[DepsT], sets: list[SavedControls], conversation_id: UUID | None
) -> ToolReturn[list[ControlSetSummary]]:
    """The saved sets as a listing tool returns them, this conversation's first."""
    rows = [control_set_summary(cs, conversation_id) for cs in sets]
    here = sum(row.saved_here for row in rows)
    return with_summary(
        sorted(rows, key=lambda row: not row.saved_here),
        f"{count_noun(len(rows), 'control set')}, {here} saved in this conversation",
        ctx=ctx,
    )


async def list_control_sets(
    ctx: RunContext[AgentDeps],
) -> ToolReturn[list[ControlSetSummary]]:
    """List the control sets attached to this conversation, the ones it saved
    first and marked ``savedHere``. A control test runs on one of them, by its
    ``control_set_id``, and on no other. An empty list means no control test
    runs. This saves nothing."""
    deps = ctx.deps
    attached = {held.id for held in deps.verification_scope.control_sets}
    sets = (
        await saved_control_sets(
            deps.db_session_factory, site_id=deps.site_id, user_id=deps.user_id
        )
        if attached
        else []
    )
    return listed_control_sets(
        ctx,
        [s for s in sets if s.control_set_id in attached],
        deps.conversation_id,
    )
