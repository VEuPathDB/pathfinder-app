"""The Lead's VERIFY dispatch tool, and the digest the ledger holds it to."""

from __future__ import annotations

from dataclasses import dataclass

from assistant_core.graph.tool_summary import count_noun
from pydantic_ai import RunContext
from veupathdb.domain.strategy import StepKind

from pathfinder.ai.agents.tool_vocabulary import build_tool_repetition_guard
from pathfinder.ai.graph.state import (
    FailureCause,
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
    digest_held_to_the_rows,
    structure_contradiction,
)
from pathfinder.ai.lead.ledger_sections import unexpressed_words
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import (
    PhaseRun,
    SubAgentApprovalWait,
    SubAgentResume,
    stream_sub_agent,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.lead.verification_scope import review_record, verification_scope
from pathfinder.ai.lead.verify_review import (
    review_held_to_the_turn,
)
from pathfinder.domain.caveats import (
    BuildCaveat,
    Caveat,
    Gap,
    check_gaps,
    measured_caveats,
)
from pathfinder.domain.constraint_check import ConstraintCheck, shortfalls
from pathfinder.domain.evidence import SAMPLED_GENE_LIMIT, VerificationReview
from pathfinder.domain.question_rows import without_questions
from pathfinder.domain.separation import AttachedControls
from pathfinder.domain.shown_requirements import (
    answered_by_uploads,
    held_to_the_records,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.services.eda.analysis_kinds import unread_analyses
from pathfinder.services.strategies.bound_uploads import uploads_the_specs_run_on
from pathfinder.services.strategies.data_marks import marks_with_uploads
from pathfinder.services.strategies.text_queries import (
    search_definitions,
    text_query_criteria,
)


@dataclass(frozen=True)
class SearchStep:
    """A step that runs a search, whose columns a check reads."""

    step_id: str
    wdk_step_id: int


@dataclass(frozen=True)
class RootSample:
    """The steps a check reads: each search step's columns, and the root it
    samples for a criterion no column shows."""

    step_id: str
    wdk_step_id: int
    count: int | None
    search_steps: tuple[SearchStep, ...] = ()


def root_sample(deps: LeadDeps) -> RootSample | None:
    """The strategy's root on the site, or None before a push."""
    session = deps.runtime.strategy_session
    sync, graph = session.sync_state, session.get_graph(None)
    root = None if sync is None else sync.wdk_root_step_id
    if sync is None or root is None:
        return None
    step_id = next((s for s, w in sync.wdk_step_ids.items() if w == root), None)
    if step_id is None:
        return None
    searched = (
        []
        if graph is None
        else [
            SearchStep(step_id=sid, wdk_step_id=sync.wdk_step_ids[sid])
            for sid, step in graph.steps.items()
            if step.kind is not StepKind.COMBINE
            and step.search_name
            and sid in sync.wdk_step_ids
        ]
    )
    return RootSample(
        step_id=step_id,
        wdk_step_id=root,
        count=sync.step_counts.get(step_id),
        search_steps=tuple(searched),
    )


def _columns_line(root: RootSample) -> str | None:
    """The search steps whose columns the check reads first, or None when
    there is none or the root holds no gene."""
    if not root.search_steps or root.count == 0:
        return None
    calls = "; ".join(
        f"read_step_columns(wdk_step_id={s.wdk_step_id}) for {s.step_id}"
        for s in root.search_steps
    )
    return f"Read the columns of each search step first: {calls}."


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
        f"{named}. For a criterion whose step shows no column, sample it with "
        f"get_sample_records(wdk_step_id={root.wdk_step_id}, limit={limit})."
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
        columns = _columns_line(root)
        lines.extend([*([] if columns is None else [columns]), _sample_line(root)])
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
    agent_deps.tool_repetition_guard = build_tool_repetition_guard()
    domain = deps.state.domain
    site_id = deps.runtime.site_id
    sheets = await search_definitions(site_id, domain.operational_spec)
    uploads = await uploads_the_specs_run_on(site_id, [domain.operational_spec], sheets)
    domain.data_marks = await marks_with_uploads(
        site_id, [domain.operational_spec], uploads
    )
    run = PhaseRun(
        "verification", work_order(reason, scope.controls, root_sample(deps))
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
        markers.verification_stopped = True
        return verification_stopped(deps.last_phase_stop)
    graph = deps.runtime.strategy_session.get_graph(None)
    # The pending checks are the strategy's to state, never the checker's.
    pending = [] if graph is None else unread_analyses(graph)
    review = held_to_the_records(
        answered_by_uploads(
            review_held_to_the_turn(
                without_questions(
                    delta.digest.review, scope.messages, domain.researcher_asks
                ),
                review_record(deps, scope.messages),
            ),
            {c: u.name for c, u in uploads.items()},
        ),
        text_query_criteria(domain.operational_spec, sheets),
    )
    computed = _study_checks(deps)
    findings = _findings(deps, review, computed)
    digest = _held(
        delta.digest.model_copy(
            update={
                "pending_checks": pending,
                "constraint_report": computed,
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
            *(gap.sentence for gap in self.gaps if gap.fails_the_check),
        ]
        return "; ".join(found) if found else None

    def cause(self) -> FailureCause | None:
        breaks_structure = any(gap.kind == "structure" for gap in self.gaps)
        return FailureCause.STRUCTURE_VIOLATION if breaks_structure else None


def _study_checks(deps: LeadDeps) -> list[ConstraintCheck]:
    """The study-step checks this turn computed, for the steps the strategy holds."""
    graph = deps.runtime.strategy_session.get_graph(None)
    held = {} if graph is None else graph.steps
    return [
        check
        for step_id, checks in deps.state.turn_markers.study_checks.items()
        if step_id in held
        for check in checks
    ]


def _findings(
    deps: LeadDeps, review: VerificationReview, computed: list[ConstraintCheck]
) -> _Findings:
    """The build's counts when it does not support a success, and every gap."""
    ledger = derive_ledger(deps.state, deps.intent)
    spec = deps.state.domain.operational_spec
    retired = [r.grounded() for r in deps.state.domain.retired_requirements]
    return _Findings(
        gaps=[
            *check_gaps(
                structure=structure_contradiction(deps.state.domain.requirements, spec),
                words=unexpressed_words(spec),
                review=review,
                requirements=[*ledger.constraints.grounded, *retired],
                asked=[q.question for q in deps.state.domain.answered_questions],
            ),
            *shortfalls(computed),
        ],
        build=build_contradiction(
            ledger.build,
            built_step_count=len(deps.runtime.strategy_session.wdk_step_ids()),
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
            frozenset(session.wdk_step_ids()),
        ),
        column_fits=review.column_fits,
    )


def _held(digest: VerificationDigest, findings: _Findings) -> VerificationDigest:
    """Hold the verdict to what the ledger recorded, both ways.

    The digest decides the memory auto-write and the eval verdict, so a success
    the findings do not support fails, and a failure with no finding passes
    when the held rows are each shown met.
    """
    sentence = findings.sentence()
    if sentence is None:
        return digest_held_to_the_rows(digest)
    if not digest.success:
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
