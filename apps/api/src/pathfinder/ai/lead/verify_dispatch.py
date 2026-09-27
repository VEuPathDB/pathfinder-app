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
from pathfinder.ai.lead.deltas import VerificationDelta, VerificationStopped
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
)
from pathfinder.ai.lead.dispatch_messages import stop_phrase
from pathfinder.ai.lead.evidence_card import (
    judged_control_tests,
    publish_evidence_card,
)
from pathfinder.ai.lead.ledger import (
    build_contradiction,
    digest_held_to_the_build,
    structure_contradiction,
)
from pathfinder.ai.lead.ledger_sections import unexpressed_words
from pathfinder.ai.lead.phase_stop import PhaseStop
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
from pathfinder.domain.caveats import (
    BuildCaveat,
    Caveat,
    Gap,
    check_gaps,
    measured_caveats,
)
from pathfinder.domain.evidence import SAMPLED_GENE_LIMIT, VerificationReview
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
            f"'{text.word}' in [{text.criterion_id or 'dropped'}] {text.stated_in}"
            for text in (spec.unexpressed() if spec is not None else [])
        ],
        breaches=[row.note for row in breached_rows(review_record(deps, messages))],
        check_id=check_id,
        last_card=deps.state.domain.card_of_the_strategy(),
        controls=deps.state.domain.attached_controls,
        control_sets=list(deps.state.domain.control_sets),
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
    """VERIFY's work order: the root it samples, and the saved control set an
    adopted strategy was measured on."""
    lines = [
        f"Verification work order: {reason}",
        "Inspect the built strategy. Return a VerificationDelta.",
    ]
    if root is not None:
        lines.append(_sample_line(root))
    if controls is not None:
        lines.append(
            "The strategy was adopted from a separation run. Run "
            "run_control_tests_on_step on its root step with control_set_id "
            f"{controls.control_set_id}, the saved set it was measured on: "
            f"{len(controls.positives)} positive and {len(controls.negatives)} "
            "negative controls."
        )
    return "\n".join(lines)


async def run_verification(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
    resume: SubAgentResume | None = None,
) -> VerificationDelta | VerificationStopped | SubAgentApprovalWait:
    """Run verification and record its digest, on a fresh or a resumed dispatch."""
    markers = deps.state.turn_markers
    markers.verification_dispatched = True
    markers.verification_stopped = False
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
        markers.verification_stopped = True
        return verification_stopped(deps.last_phase_stop)
    graph = deps.runtime.strategy_session.get_graph(None)
    # The pending checks are the strategy's to state, never the checker's.
    pending = [] if graph is None else unread_analyses(graph)
    review = review_held_to_the_turn(
        delta.digest.review, review_record(deps, scope.messages)
    )
    findings = _findings(deps, review)
    digest = _held(
        delta.digest.model_copy(
            update={
                "pending_checks": pending,
                "review": review,
                "gaps": findings.gaps,
                "caveats": _caveats(deps, review, findings.build),
            }
        ),
        findings,
    )
    revision = strategy_revision(live_tree(graph))
    deps.state.domain.record_verdict(digest, revision=revision)
    deps.state.turn_markers.verified = digest.passed
    await publish_evidence_card(
        deps,
        check_id=parent_tool_call_id,
        revision=revision,
        pending_checks=digest.pending_checks,
        review=digest.review,
    )
    return VerificationDelta(digest=digest)


def verification_stopped(stop: PhaseStop | None) -> VerificationStopped:
    """Report a check that ended before it returned a digest."""
    why = "stopped before it finished" if stop is None else stop_phrase(stop)
    return VerificationStopped(
        stop=stop,
        summary=(
            f"VERIFY {why}, so it recorded no verdict and the strategy is not "
            "verified. Tell the user the check did not finish and why, and ask "
            "whether to run it again."
        ),
    )


@dataclass(frozen=True)
class _Findings:
    """What the build, the spec and the review give against a success."""

    gaps: list[Gap]
    build: BuildCaveat | None

    def sentence(self) -> str | None:
        """Every finding in one clause, or None when there is none."""
        found = [
            *([] if self.build is None else [self.build.sentence]),
            *(gap.sentence for gap in self.gaps),
        ]
        return "; ".join(found) if found else None

    def cause(self) -> FailureCause | None:
        breaks_structure = any(gap.kind == "structure" for gap in self.gaps)
        return FailureCause.STRUCTURE_VIOLATION if breaks_structure else None


def _findings(deps: LeadDeps, review: VerificationReview) -> _Findings:
    """The build's counts when it does not support a success, and every gap."""
    ledger = derive_ledger(deps.state, deps.intent)
    spec = deps.state.domain.operational_spec
    return _Findings(
        gaps=check_gaps(
            structure=structure_contradiction(deps.state.domain.requirements, spec),
            words=unexpressed_words(spec),
            review=review,
        ),
        build=build_contradiction(
            ledger.build,
            built_step_count=len(live_wdk_step_ids(deps.runtime.strategy_session)),
        ),
    )


def _caveats(
    deps: LeadDeps, review: VerificationReview, build: BuildCaveat | None
) -> list[Caveat]:
    """What the check measured short of the request, read from the records."""
    session = deps.runtime.strategy_session
    return measured_caveats(
        build=build,
        controls=judged_control_tests(
            deps.state.turn_markers.control_tests,
            frozenset(live_wdk_step_ids(session)),
        ),
        genes=review.sampled_genes,
    )


def _held(digest: VerificationDigest, findings: _Findings) -> VerificationDigest:
    """Hold the verdict to what the ledger recorded.

    The digest decides the memory auto-write and the eval verdict, so a success
    it cannot support is corrected here rather than at each reader.
    """
    sentence = findings.sentence()
    if sentence is None or not digest.success:
        return digest
    return digest_held_to_the_build(digest, sentence, failure_cause=findings.cause())


async def verify_strategy(
    ctx: RunContext[LeadDeps],
    reason: str,
) -> VerificationDelta | VerificationStopped:
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
