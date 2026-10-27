"""The Lead's VERIFY dispatch tool, and the verdict the site's answers decide."""

from __future__ import annotations

from dataclasses import dataclass

from assistant_core.graph.tool_summary import count_noun
from pydantic_ai import RunContext

from pathfinder.ai.agents.tool_vocabulary import build_tool_repetition_guard
from pathfinder.ai.graph.state import (
    FailureCause,
    PhaseDisposition,
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
from pathfinder.ai.lead.ledger import build_contradiction
from pathfinder.ai.lead.ledger_sections import unexpressed_words
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import (
    PhaseRun,
    SubAgentApprovalWait,
    SubAgentResume,
    stream_sub_agent,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.lead.verification_scope import verification_scope
from pathfinder.ai.lead.verify_checks import read_the_columns, site_checks
from pathfinder.domain.caveats import BuildCaveat, Gap, check_gaps, measured_caveats
from pathfinder.domain.column_fit import ColumnFit
from pathfinder.domain.evidence import SAMPLED_GENE_LIMIT
from pathfinder.domain.separation import AttachedControls
from pathfinder.domain.site_checks import SiteCheck, failed
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.services.eda.analysis_kinds import unread_analyses
from pathfinder.services.strategies.bound_uploads import uploads_the_specs_run_on
from pathfinder.services.strategies.data_marks import marks_with_uploads
from pathfinder.services.strategies.search_sheets import search_definitions


@dataclass(frozen=True)
class RootSample:
    """The root a check samples to say what the result's records look like."""

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
    return RootSample(
        step_id=step_id, wdk_step_id=root, count=sync.step_counts.get(step_id)
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
        f"{named}. To say what its records look like, sample it with "
        f"get_sample_records(wdk_step_id={root.wdk_step_id}, limit={limit})."
    )


def _check_lines(
    checks: list[SiteCheck], fits: list[ColumnFit], notes: list[str]
) -> list[str]:
    if not checks and not fits and not notes:
        return []
    return [
        "The runtime read the strategy on the site. These checks decide the verdict:",
        *(f"- [{c.status}] {c.subject}: {c.evidence}" for c in checks),
        *(f"- [column] {fit.sentence}" for fit in fits),
        *(f"- [no column] {note}" for note in notes),
    ]


def work_order(
    reason: str,
    controls: AttachedControls | None,
    root: RootSample | None,
    checks: list[SiteCheck] | None = None,
    fits: list[ColumnFit] | None = None,
    notes: list[str] | None = None,
) -> str:
    """VERIFY's work order: the checks the runtime ran, the root it may sample,
    and the saved control set an adopted strategy was measured on."""
    lines = [
        f"Verification work order: {reason}",
        "Inspect the built strategy. Return a VerificationDelta.",
        *_check_lines(checks or [], fits or [], notes or []),
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


def _live_fits(deps: LeadDeps) -> list[ColumnFit]:
    live = frozenset(deps.runtime.strategy_session.wdk_step_ids())
    return [f for f in deps.state.turn_markers.column_fits if f.wdk_step_id in live]


async def run_verification(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
    resume: SubAgentResume | None = None,
) -> VerificationDelta | VerificationStopped | SubAgentApprovalWait:
    """Run the checks on the site, then the checker, and record the verdict the
    checks decide, on a fresh or a resumed dispatch."""
    markers = deps.state.turn_markers
    markers.verification_dispatched = True
    # A check counts as stopped until its digest is recorded.
    markers.verification_stopped = True
    agent_deps = agent_deps_for(deps, call_id=parent_tool_call_id)
    scope = verification_scope(deps, check_id=parent_tool_call_id)
    agent_deps.verification_scope = scope
    agent_deps.tool_repetition_guard = build_tool_repetition_guard()
    domain = deps.state.domain
    site_id = deps.runtime.site_id
    sheets = await search_definitions(site_id, domain.operational_spec)
    uploads = await uploads_the_specs_run_on(site_id, [domain.operational_spec], sheets)
    domain.data_marks = await marks_with_uploads(
        site_id, [domain.operational_spec], uploads
    )
    notes = await read_the_columns(deps, agent_deps)
    checks = await site_checks(deps)
    run = PhaseRun(
        "verification",
        work_order(
            reason, scope.controls, root_sample(deps), checks, _live_fits(deps), notes
        ),
    )
    delta = await stream_sub_agent(
        run=run,
        agent_deps=agent_deps,
        parent_tool_call_id=parent_tool_call_id,
        expected_output_type=VerificationDelta,
        deps=deps,
        resume=resume,
    )
    if delta is None and _stopped_by_the_provider(deps):
        # The request, not the check, failed, so the system sends it once more.
        deps.verify_retried_after_stop = True
        delta = await stream_sub_agent(
            run=run,
            agent_deps=agent_deps,
            parent_tool_call_id=parent_tool_call_id,
            expected_output_type=VerificationDelta,
            deps=deps,
        )
    if isinstance(delta, SubAgentApprovalWait):
        return delta
    apply_agent_state(deps, agent_deps)
    if delta is None:
        return verification_stopped(deps.last_phase_stop)
    graph = deps.runtime.strategy_session.get_graph(None)
    digest = _decided(deps, delta.digest, checks)
    revision = strategy_revision(live_tree(graph))
    deps.state.domain.record_verdict(digest, revision=revision)
    markers.verification_stopped = False
    markers.verified = digest.passed
    await publish_evidence_card(
        deps,
        check_id=parent_tool_call_id,
        revision=revision,
        pending_checks=digest.pending_checks,
        review=digest.review,
    )
    return VerificationDelta(digest=digest)


def _stopped_by_the_provider(deps: LeadDeps) -> bool:
    stop = deps.last_phase_stop
    return (
        stop is not None
        and stop.reason is PhaseStopReason.PROVIDER
        and not deps.verify_retried_after_stop
    )


def verification_stopped(stop: PhaseStop | None) -> VerificationStopped:
    """Report a check that ended before it returned a digest."""
    why = "stopped before it finished" if stop is None else stop_phrase(stop)
    return VerificationStopped(
        stop=stop,
        summary=(
            f"VERIFY {why}, so it recorded no verdict and the strategy is not "
            "verified. Tell the user the check did not finish and why, and ask "
            "whether to run it again. Set `unverifiedReason` to why the check "
            "did not finish."
        ),
    )


def _gaps(deps: LeadDeps, checks: list[SiteCheck]) -> list[Gap]:
    ledger = derive_ledger(deps.state, deps.intent)
    retired = [r.grounded() for r in deps.state.domain.retired_requirements]
    return [
        *check_gaps(
            words=unexpressed_words(deps.state.domain.operational_spec),
            requirements=[*ledger.constraints.grounded, *retired],
        ),
        *failed(checks),
    ]


def _build(deps: LeadDeps) -> BuildCaveat | None:
    ledger = derive_ledger(deps.state, deps.intent)
    live = frozenset(deps.runtime.strategy_session.wdk_step_ids())
    return build_contradiction(ledger.build, built_step_count=len(live))


def _verdict(build: BuildCaveat | None, gaps: list[Gap]) -> str:
    found = [
        *([] if build is None else [build.sentence]),
        *(gap.sentence for gap in gaps if gap.fails_the_check),
    ]
    return "; ".join(found) or "No check of the strategy on the site failed"


def _decided(
    deps: LeadDeps, checked: VerificationDigest, checks: list[SiteCheck]
) -> VerificationDigest:
    session = deps.runtime.strategy_session
    graph = session.get_graph(None)
    gaps = _gaps(deps, checks)
    build = _build(deps)
    success = build is None and not any(gap.fails_the_check for gap in gaps)
    fits = _live_fits(deps)
    return checked.model_copy(
        update={
            "success": success,
            "disposition": PhaseDisposition.DONE
            if success
            else PhaseDisposition.HANDOFF,
            "handoff_to": None if success else checked.handoff_to,
            "failure_cause": (
                FailureCause.STRUCTURE_VIOLATION
                if any(check.breaks_the_structure for check in checks)
                else None
            ),
            "reason": _verdict(build, gaps),
            "pending_checks": [] if graph is None else unread_analyses(graph),
            "review": checked.review.model_copy(
                update={"checks": checks, "column_fits": fits}
            ),
            "gaps": gaps,
            "caveats": measured_caveats(
                build=build,
                controls=judged_control_tests(
                    deps.state.turn_markers.control_tests,
                    frozenset(session.wdk_step_ids()),
                ),
                column_fits=fits,
            ),
        }
    )


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
