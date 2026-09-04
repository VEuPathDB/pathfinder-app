"""The Lead's VERIFY dispatch tool, and the digest the ledger holds it to."""

from __future__ import annotations

from pydantic_ai import RunContext

from pathfinder.ai.graph.runtime import VerificationScope
from pathfinder.ai.graph.state import FailureCause, VerificationDigest
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
)
from pathfinder.ai.lead.ledger import (
    build_contradiction,
    digest_held_to_the_build,
    structure_contradiction,
)
from pathfinder.ai.lead.sub_agent_stream import (
    PhaseRun,
    SubAgentApprovalWait,
    SubAgentResume,
    stream_sub_agent,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.tools.toolsets._dynamic import live_wdk_step_ids


def verification_scope(
    deps: LeadDeps, *, enrichment_requested: bool
) -> VerificationScope:
    """What this turn changed, as the verification playbook reads it."""
    diff = derive_ledger(deps.state, deps.intent).frame.spec_diff()
    if diff is None:
        return VerificationScope(enrichment_requested=enrichment_requested)
    return VerificationScope(
        criteria_touched=diff.touched_count(),
        is_edit=True,
        enrichment_requested=enrichment_requested,
    )


async def run_verification(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
    enrichment_requested: bool = False,
    resume: SubAgentResume | None = None,
) -> VerificationDelta | SubAgentApprovalWait:
    """Run verification and record its digest, on a fresh or a resumed dispatch."""
    deps.state.turn_markers.verification_dispatched = True
    work_order = (
        f"Verification work order: {reason}\n"
        "Inspect the built strategy. Return a VerificationDelta."
    )
    agent_deps = agent_deps_for(deps)
    agent_deps.verification_scope = verification_scope(
        deps, enrichment_requested=enrichment_requested
    )
    delta = await stream_sub_agent(
        run=PhaseRun("verification", work_order),
        agent_deps=agent_deps,
        parent_tool_call_id=parent_tool_call_id,
        expected_output_type=VerificationDelta,
        deps=deps,
        resume=resume,
    )
    if isinstance(delta, SubAgentApprovalWait):
        return delta
    apply_agent_state(deps, agent_deps)
    if delta is None:
        msg = "Verification sub-agent did not return a VerificationDelta."
        raise TypeError(msg)
    digest = _digest_the_build_supports(deps, delta.digest)
    deps.state.domain.verification_digest = digest
    deps.state.turn_markers.verified = digest.success
    return VerificationDelta(digest=digest)


def _digest_the_build_supports(
    deps: LeadDeps, digest: VerificationDigest
) -> VerificationDigest:
    """Hold the verdict to what the ledger recorded.

    The digest decides the reply, the memory auto-write and the eval verdict,
    so a success it cannot support is corrected here rather than at each
    reader.
    """
    if not digest.success:
        return digest
    ledger = derive_ledger(deps.state, deps.intent)
    contradiction = build_contradiction(
        ledger.build,
        built_step_count=len(live_wdk_step_ids(deps.runtime.strategy_session)),
    )
    if contradiction is not None:
        return digest_held_to_the_build(digest, contradiction)
    structural = structure_contradiction(
        deps.state.domain.requirements,
        deps.state.domain.operational_spec,
    )
    if structural is None:
        return digest
    return digest_held_to_the_build(
        digest, structural, failure_cause=FailureCause.STRUCTURE_VIOLATION
    )


async def verify_strategy(
    ctx: RunContext[LeadDeps],
    reason: str,
    *,
    enrichment_requested: bool = False,
) -> VerificationDelta:
    """Run the verification sub-agent on the built strategy.

    This sub-agent owns every post-build check, so route a user's request for
    one here through ``reason``: GO, pathway and word enrichment on a gene
    set; control tests on a step or a search; parameter optimization; sample
    records from a result; result export. None of these are Lead tools.

    Set ``enrichment_requested`` only when the user asked for GO, pathway or
    word enrichment in this message. It runs for minutes on a worker, so an
    edit turn that did not ask for it is verified by its counts instead.

    Available once the strategy holds a step, and until a verification of this
    turn reports success.
    """
    tool_call_id = dispatch_call_id(ctx)
    result = await run_verification(
        deps=ctx.deps,
        parent_tool_call_id=tool_call_id,
        reason=reason,
        enrichment_requested=enrichment_requested,
    )
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(ctx.deps, tool_call_id, result)
    return result
