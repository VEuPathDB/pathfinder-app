"""The Lead's VERIFY dispatch tool, and the digest the ledger holds it to."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import RunContext

from pathfinder.ai.graph.runtime import VerificationScope
from pathfinder.ai.graph.state import FailureCause, VerificationDigest
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
    framing_goal,
)
from pathfinder.ai.lead.evidence_card import publish_evidence_card
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
from pathfinder.domain.evidence import EvidenceVerdict
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.services.eda.analysis_kinds import unread_analyses


def verification_scope(deps: LeadDeps, *, check_id: str) -> VerificationScope:
    """The request this turn answers and the check that answers it, as VERIFY reads them."""
    return VerificationScope(
        request=framing_goal(deps.state),
        check_id=check_id,
        last_card=deps.state.domain.card_of_the_strategy(),
    )


async def run_verification(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
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
        deps, check_id=parent_tool_call_id
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
    graph = deps.runtime.strategy_session.get_graph(None)
    # The pending checks are the strategy's to state, never the checker's.
    pending = [] if graph is None else unread_analyses(graph)
    held = _digest_the_build_supports(
        deps, delta.digest.model_copy(update={"pending_checks": pending})
    )
    digest = held.digest
    revision = strategy_revision(live_tree(graph))
    deps.state.domain.record_verdict(digest, revision=revision)
    deps.state.turn_markers.verified = digest.passed
    await publish_evidence_card(
        deps,
        check_id=parent_tool_call_id,
        revision=revision,
        verdict=EvidenceVerdict(
            supported=digest.success,
            pending_checks=digest.pending_checks,
            refused_because=held.refused_because,
        ),
    )
    return VerificationDelta(digest=digest)


@dataclass(frozen=True)
class _HeldDigest:
    """The digest the ledger lets stand, and the reason it refused a success."""

    digest: VerificationDigest
    refused_because: str | None = None


def _digest_the_build_supports(
    deps: LeadDeps, digest: VerificationDigest
) -> _HeldDigest:
    """Hold the verdict to what the ledger recorded.

    The digest decides the reply, the memory auto-write and the eval verdict,
    so a success it cannot support is corrected here rather than at each
    reader.
    """
    if not digest.success:
        return _HeldDigest(digest)
    ledger = derive_ledger(deps.state, deps.intent)
    contradiction = build_contradiction(
        ledger.build,
        built_step_count=len(live_wdk_step_ids(deps.runtime.strategy_session)),
    )
    if contradiction is not None:
        return _HeldDigest(
            digest_held_to_the_build(digest, contradiction), contradiction
        )
    structural = structure_contradiction(
        deps.state.domain.requirements,
        deps.state.domain.operational_spec,
    )
    if structural is None:
        return _HeldDigest(digest)
    return _HeldDigest(
        digest_held_to_the_build(
            digest, structural, failure_cause=FailureCause.STRUCTURE_VIOLATION
        ),
        structural,
    )


async def verify_strategy(
    ctx: RunContext[LeadDeps],
    reason: str,
) -> VerificationDelta:
    """Run the verification sub-agent on the built strategy.

    This sub-agent owns every post-build check, so route a user's request for
    one here through ``reason``: control tests on a step or a search;
    parameter optimization; sample records from a result; result export. Each
    check leaves an evidence card in the thread. GO, pathway and word
    enrichment run on the site, from the step page the card links.

    Available once the strategy holds a step, and until a verification of this
    turn reports success.
    """
    tool_call_id = dispatch_call_id(ctx)
    result = await run_verification(
        deps=ctx.deps,
        parent_tool_call_id=tool_call_id,
        reason=reason,
    )
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(ctx.deps, tool_call_id, result)
    return result
