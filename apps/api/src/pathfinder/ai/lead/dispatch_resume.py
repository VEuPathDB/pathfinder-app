"""Finish the dispatch a user answered, from the arguments it was called with.

The approval suspends the sub-agent inside a Lead tool, so the re-entry runs
the same dispatch again rather than a shorter version of it.
"""

from __future__ import annotations

from assistant_core.graph.turn_state import ParkedCall
from pydantic import BaseModel, ConfigDict

from pathfinder.ai.lead.deltas import (
    EditDelta,
    FrameResult,
    RecoveryDelta,
    VerificationDelta,
)
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_dispatch import run_recovery
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification

__all__ = ["SubAgentOutcome", "resume_sub_agent"]


class _ReasonArgs(BaseModel):
    """The ``reason`` every dispatch wrapper takes."""

    model_config = ConfigDict(extra="ignore")

    reason: str = ""


class _FrameArgs(_ReasonArgs):
    expected_criteria: int = 3


class _VerifyArgs(_ReasonArgs):
    enrichment_requested: bool = False


type SubAgentOutcome = (
    FrameResult | RecoveryDelta | VerificationDelta | EditDelta | SubAgentApprovalWait
)


async def resume_sub_agent(
    *,
    deps: LeadDeps,
    approval: ParkedCall,
    resume: SubAgentResume,
) -> SubAgentOutcome:
    """Finish the dispatch the user answered, from its own arguments."""
    call_id = approval.tool_call_id
    args = dict(approval.tool_args)
    match approval.tool_name:
        case "verify_strategy":
            verify_args = _VerifyArgs.model_validate(args)
            return await run_verification(
                deps=deps,
                parent_tool_call_id=call_id,
                reason=verify_args.reason,
                enrichment_requested=verify_args.enrichment_requested,
                resume=resume,
            )
        case "recover_failed_steps":
            return await run_recovery(
                deps=deps,
                parent_tool_call_id=call_id,
                reason=_ReasonArgs.model_validate(args).reason,
                resume=resume,
            )
        case "edit_strategy":
            return await run_edit(
                deps=deps,
                parent_tool_call_id=call_id,
                reason=_ReasonArgs.model_validate(args).reason,
                resume=resume,
            )
        case "frame_problem":
            frame_args = _FrameArgs.model_validate(args)
            return await run_frame(
                deps=deps,
                parent_tool_call_id=call_id,
                work_order=frame_work_order(frame_args.reason, deps.state.user_prompt),
                expected_criteria=frame_args.expected_criteria,
                resume=resume,
            )
        case _:
            msg = f"No sub-agent dispatch named {approval.tool_name!r} to resume."
            raise RuntimeError(msg)
