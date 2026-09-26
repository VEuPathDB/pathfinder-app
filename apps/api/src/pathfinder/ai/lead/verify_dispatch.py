"""The Lead's VERIFY dispatch tool, and the digest the ledger holds it to."""

from __future__ import annotations

from dataclasses import dataclass

from assistant_core.graph.tool_summary import count_noun
from pydantic_ai import RunContext

from pathfinder.ai.agents.tool_vocabulary import build_verification_repetition_guard
from pathfinder.ai.graph.runtime import VerificationScope
from pathfinder.ai.graph.state import (
    FailureCause,
    PipelineState,
    VerificationDigest,
)
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
)
from pathfinder.ai.lead.evidence_card import publish_evidence_card
from pathfinder.ai.lead.ledger import (
    build_contradiction,
    digest_held_to_the_build,
    structure_contradiction,
)
from pathfinder.ai.lead.ledger_sections import unexpressed_words
from pathfinder.ai.lead.sub_agent_stream import (
    PhaseRun,
    SubAgentApprovalWait,
    SubAgentResume,
    stream_sub_agent,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.lead.verify_review import (
    ReviewRecord,
    breached_rows,
    review_held_to_the_turn,
)
from pathfinder.ai.tools.toolsets._dynamic import live_wdk_step_ids
from pathfinder.domain.evidence import (
    SAMPLED_GENE_LIMIT,
    EvidenceVerdict,
    VerificationReview,
)
from pathfinder.domain.separation import AttachedControls
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.services.eda.analysis_kinds import unread_analyses
from pathfinder.services.gene_records.read import gene_record_url


def request_messages(state: PipelineState) -> list[str]:
    """Every message the researcher wrote for the request, oldest first, once each."""
    domain = state.domain
    found = [domain.original_request, *domain.request_messages, state.user_prompt]
    return list(dict.fromkeys(text for text in found if text))


def review_record(deps: LeadDeps, messages: list[str]) -> ReviewRecord:
    """What this turn holds that the check's review is held to."""
    return ReviewRecord(
        messages=messages,
        requirements=deps.state.domain.requirements,
        spec=deps.state.domain.operational_spec,
        read_as=deps.state.turn_markers.retrieved_as,
        record_url=lambda gene_id: gene_record_url(deps.runtime.site_id, gene_id),
    )


def verification_scope(deps: LeadDeps, *, check_id: str) -> VerificationScope:
    """The request this turn answers and the check that answers it, as VERIFY reads them."""
    messages = request_messages(deps.state)
    spec = deps.state.domain.operational_spec
    ledger = derive_ledger(deps.state, deps.intent)
    return VerificationScope(
        messages=messages,
        stated=[line.removeprefix("- ") for line in ledger.constraints.render_stated()],
        unexpressed=[
            f"'{word}' in [{criterion.id}] {criterion.text}"
            for criterion in (spec.criteria if spec is not None else [])
            for word in criterion.unexpressed_qualifiers
        ],
        breaches=[row.note for row in breached_rows(review_record(deps, messages))],
        check_id=check_id,
        last_card=deps.state.domain.card_of_the_strategy(),
        controls=deps.state.domain.attached_controls,
    )


@dataclass(frozen=True)
class RootSample:
    """The step a check samples its genes from, and how many records it holds."""

    step_id: str
    wdk_step_id: int
    count: int | None


def root_sample(deps: LeadDeps) -> RootSample | None:
    """The strategy's root on the site, or None before a push."""
    sync = deps.runtime.strategy_session.sync_state
    root = None if sync is None else sync.wdk_root_step_id
    if sync is None or root is None:
        return None
    step_id = next((s for s, w in sync.wdk_step_ids.items() if w == root), None)
    if step_id is None:
        return None
    outcome = deps.state.domain.last_build_outcome
    return RootSample(
        step_id=step_id,
        wdk_step_id=root,
        count=None if outcome is None else outcome.root_count,
    )


def _sample_line(root: RootSample) -> str:
    """Where the check samples its genes, and how many records it reads."""
    held = "" if root.count is None else f", {count_noun(root.count, 'record')}"
    named = f"The root is {root.step_id}, step {root.wdk_step_id} on the site{held}"
    if root.count == 0:
        return f"{named}. It holds no gene to sample."
    limit = (
        SAMPLED_GENE_LIMIT
        if root.count is None
        else min(SAMPLED_GENE_LIMIT, root.count)
    )
    return (
        f"{named}. Sample it with get_sample_records("
        f"wdk_step_id={root.wdk_step_id}, limit={limit})."
    )


def work_order(
    reason: str, controls: AttachedControls | None, root: RootSample | None
) -> str:
    """VERIFY's work order: the root it samples, and each control an adopted
    strategy was measured on."""
    lines = [
        f"Verification work order: {reason}",
        "Inspect the built strategy. Return a VerificationDelta.",
    ]
    if root is not None:
        lines.append(_sample_line(root))
    if controls is not None:
        lines += [
            (
                "The strategy was adopted from a separation run. Run "
                "run_control_tests_on_step on its root step with exactly these "
                f"controls, saved as control set {controls.control_set_id}:"
            ),
            f"positive_controls: {', '.join(controls.positives)}",
            f"negative_controls: {', '.join(controls.negatives)}",
        ]
    return "\n".join(lines)


async def run_verification(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
    resume: SubAgentResume | None = None,
) -> VerificationDelta | SubAgentApprovalWait:
    """Run verification and record its digest, on a fresh or a resumed dispatch."""
    deps.state.turn_markers.verification_dispatched = True
    agent_deps = agent_deps_for(deps)
    scope = verification_scope(deps, check_id=parent_tool_call_id)
    agent_deps.verification_scope = scope
    agent_deps.tool_repetition_guard = build_verification_repetition_guard()
    delta = await stream_sub_agent(
        run=PhaseRun(
            "verification", work_order(reason, scope.controls, root_sample(deps))
        ),
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
    review = review_held_to_the_turn(
        delta.digest.review, review_record(deps, scope.messages)
    )
    held = _digest_the_build_supports(
        deps,
        delta.digest.model_copy(
            update={
                "pending_checks": pending,
                "review": review,
                "caveats": _with_the_misfits(delta.digest.caveats, review),
            }
        ),
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
        review=digest.review,
    )
    return VerificationDelta(digest=digest)


def _with_the_misfits(caveats: list[str], review: VerificationReview) -> list[str]:
    """The caveats, led by the count of sampled genes that do not fit."""
    line = review.misfit_caveat()
    if line is None or line in caveats:
        return caveats
    return [line, *caveats][:10]


@dataclass(frozen=True)
class _HeldDigest:
    """The digest the ledger lets stand, and the ledger's reason for a failure."""

    digest: VerificationDigest
    refused_because: str | None = None


@dataclass(frozen=True)
class _Refusal:
    """Why the ledger cannot support a success, and the cause it records."""

    reason: str
    cause: FailureCause | None = None


def _ledger_refusal(deps: LeadDeps, digest: VerificationDigest) -> _Refusal | None:
    """The first reason the build, the spec or the review gives against success."""
    ledger = derive_ledger(deps.state, deps.intent)
    contradiction = build_contradiction(
        ledger.build,
        built_step_count=len(live_wdk_step_ids(deps.runtime.strategy_session)),
    )
    if contradiction is not None:
        return _Refusal(contradiction)
    structural = structure_contradiction(
        deps.state.domain.requirements,
        deps.state.domain.operational_spec,
    )
    if structural is not None:
        return _Refusal(structural, FailureCause.STRUCTURE_VIOLATION)
    words = unexpressed_words(deps.state.domain.operational_spec)
    if words:
        return _Refusal(
            f"the request states {', '.join(repr(w) for w in words)}, and no search "
            f"the strategy runs can state it"
        )
    unmet = digest.review.unmet()
    if not unmet:
        return None
    return _Refusal(
        f"the check reports {count_noun(len(unmet), 'requirement')} unmet: "
        f"{', '.join(repr(row.text) for row in unmet)}"
    )


def _digest_the_build_supports(
    deps: LeadDeps, digest: VerificationDigest
) -> _HeldDigest:
    """Hold the verdict to what the ledger recorded.

    The digest decides the reply, the memory auto-write and the eval verdict,
    so a success it cannot support is corrected here rather than at each
    reader. A failure the check found keeps its digest and takes the reason.
    """
    refusal = _ledger_refusal(deps, digest)
    if refusal is None:
        return _HeldDigest(digest)
    if not digest.success:
        return _HeldDigest(digest, refusal.reason)
    held = digest_held_to_the_build(digest, refusal.reason, failure_cause=refusal.cause)
    return _HeldDigest(held, refusal.reason)


async def verify_strategy(
    ctx: RunContext[LeadDeps],
    reason: str,
) -> VerificationDelta:
    """Run the verification sub-agent on the built strategy.

    This sub-agent owns every post-build check, so route a user's request for
    one here through ``reason``: control tests on a step or a search;
    parameter optimization; sample records from a result; result export. Each
    check leaves an evidence card in the conversation. GO, pathway and word
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
