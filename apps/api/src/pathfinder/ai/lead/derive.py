from __future__ import annotations

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    ConstraintSection,
    FrameSection,
    RecoveryKind,
    VerificationSection,
    assumption_constraints,
    unexpressed_constraints,
)
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.domain.caveats import caveats_for
from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    StepPushFailure,
)
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    merge_constraints,
    provisional_constraints,
)
from pathfinder.domain.unmet_requirements import unmet_requirement_keys

_TRANSIENT_MARKERS: frozenset[str] = frozenset(
    {
        "5xx",
        "503",
        "504",
        "502",
        "timeout",
        "timed out",
        "connection",
        "network",
    }
)
_VOCAB_MARKERS: frozenset[str] = frozenset(
    {
        "vocab",
        "validoptions",
        "valid options",
        "parameter",
        "param",
        "value",
    }
)
_SEARCH_INVALID_MARKERS: frozenset[str] = frozenset(
    {
        "unknown search",
        "invalid search",
        "search not found",
    }
)


def derive_ledger(
    state: PipelineState,
    intent: UserIntent | None,
    *,
    phase_stop: PhaseStop | None = None,
) -> InvestigationLedger:
    """Pure derivation of the Ledger from PipelineState + the latest intent.

    No I/O. The Lead calls this on every turn. Sub-agents do NOT call it -
    they receive scoped slices via typed work orders from the Lead.

    ``phase_stop`` is why the turn's last dispatch ended without a delta. It
    lives for one turn, so the caller holding it passes it in.
    """
    return InvestigationLedger(
        user_intent=intent,
        frame=FrameSection(
            spec=state.domain.operational_spec,
            spec_before_turn=state.domain.spec_before_turn,
            open_questions=state.domain.open_questions,
            named_readings=state.domain.named_readings,
            picked_readings=state.domain.picked_readings,
        ),
        build=_derive_build_section(state),
        verification=_derive_verification_section(state),
        constraints=_derive_constraint_section(state, intent),
        declined_proposal=state.domain.declined_proposal,
        phase_stop=phase_stop,
        open_analysis=state.domain.open_eda_analysis,
    )


def _thread_requirements(
    state: PipelineState, intent: UserIntent | None
) -> list[Constraint]:
    """Every requirement the thread has stated, this turn's included.

    The accumulation is deduped on the dimension AND the value, so two
    free-form requirements never collapse into one.
    """
    stated = list(state.domain.requirements)
    seen = {(c.kind, c.requested_value) for c in stated}
    for constraint in intent.explicit_constraints if intent else []:
        key = (constraint.kind, constraint.requested_value)
        if key not in seen:
            seen.add(key)
            stated.append(constraint)
    return stated


def _carried_requirements(
    state: PipelineState, intent: UserIntent | None
) -> list[Constraint]:
    """The thread's requirements that the latest message did not restate."""
    restated = {
        (c.kind, c.requested_value)
        for c in (intent.explicit_constraints if intent else [])
    }
    return [
        c
        for c in state.domain.requirements
        if (c.kind, c.requested_value) not in restated
    ]


def _as_checked(grounded: GroundedConstraint, unmet: set[str]) -> GroundedConstraint:
    if grounded.status is not ConstraintStatus.GROUNDED:
        return grounded
    if grounded.constraint.key not in unmet:
        return grounded
    return grounded.model_copy(
        update={
            "status": ConstraintStatus.UNGROUNDABLE,
            "note": "a check of the strategy on the site failed it",
        }
    )


def _merged_requirements(
    state: PipelineState, intent: UserIntent | None
) -> list[Constraint]:
    spec = state.domain.operational_spec
    # A retired requirement stays retired whatever the spec still says of it.
    retired = {r.constraint.key for r in state.domain.retired_requirements}
    provisional = [c for c in spec.constraints if c.key not in retired] if spec else []
    requirements = _thread_requirements(state, intent)
    merged = merge_constraints(provisional, requirements)
    kept = {(c.kind, c.requested_value) for c in merged}
    merged.extend(c for c in requirements if (c.kind, c.requested_value) not in kept)
    return merged


def _unexpressed(state: PipelineState) -> list[GroundedConstraint]:
    retired = {r.constraint.key for r in state.domain.retired_requirements}
    return [
        g
        for g in unexpressed_constraints(state.domain.operational_spec)
        if g.constraint.key not in retired
    ]


def grounded_requirements(
    state: PipelineState, intent: UserIntent | None
) -> list[GroundedConstraint]:
    spec = state.domain.operational_spec
    merged = _merged_requirements(state, intent)
    if spec is None:
        return provisional_constraints(merged)
    held_open = {g.constraint.key for g in _unexpressed(state)}
    return [
        g
        for g in ground_against_spec(merged, spec, marks=state.domain.data_marks)
        if g.constraint.key not in held_open
    ]


def _derive_constraint_section(
    state: PipelineState, intent: UserIntent | None
) -> ConstraintSection:
    spec = state.domain.operational_spec
    requirements = _thread_requirements(state, intent)
    recommended = list(state.domain.recommendations)
    composed = [
        c for c in requirements if c.source is not ConstraintSource.USER_EXPLICIT
    ]
    carried = _carried_requirements(state, intent)
    assumed = [*assumption_constraints(spec), *_unexpressed(state)]
    if not _merged_requirements(state, intent):
        return ConstraintSection(
            grounded=assumed,
            recommended=recommended,
            carried=carried,
            composed=composed,
        )
    if spec is None:
        return ConstraintSection(
            grounded=grounded_requirements(state, intent),
            recommended=recommended,
            carried=carried,
            composed=composed,
        )
    verdict = state.turn_verdict
    unmet = set() if verdict is None else set(unmet_requirement_keys(verdict.gaps))
    return ConstraintSection(
        grounded=[
            *(_as_checked(g, unmet) for g in grounded_requirements(state, intent)),
            *assumed,
        ],
        recommended=recommended,
        carried=carried,
        composed=composed,
    )


def _derive_build_section(state: PipelineState) -> BuildSection:
    outcome = state.domain.last_build_outcome
    if outcome is None:
        return BuildSection(stale_build=state.domain.stale_build)
    return BuildSection(
        outcome=outcome,
        stale_build=state.domain.stale_build,
        pushed_count=len(outcome.pushed_step_ids),
        failed_count=len(outcome.failed_steps),
        skipped_count=len(outcome.skipped_step_ids),
        zero_result_steps=list(outcome.zero_step_ids),
        needs_recovery=not outcome.fully_succeeded,
        recovery_kind=_recovery_kind(outcome),
    )


def _recovery_kind(outcome: BuildOutcome) -> RecoveryKind:
    """What a failed build needs next. A build that fully pushed needs nothing."""
    if outcome.fully_succeeded:
        return "none"
    classified = {_classify_failure(f) for f in outcome.failed_steps}
    if "transient_retry" in classified:
        return "transient_retry"
    if "search_replan" in classified:
        return "search_replan"
    if "param_replan" in classified:
        return "param_replan"
    return "user_clarify"


def _classify_failure(failure: StepPushFailure) -> RecoveryKind:
    err = failure.error.casefold()
    if any(marker in err for marker in _TRANSIENT_MARKERS):
        return "transient_retry"
    if any(marker in err for marker in _SEARCH_INVALID_MARKERS):
        return "search_replan"
    if any(marker in err for marker in _VOCAB_MARKERS):
        return "param_replan"
    return "user_clarify"


def _derive_verification_section(state: PipelineState) -> VerificationSection:
    digest = state.turn_verdict
    if digest is None:
        return VerificationSection()
    return VerificationSection(
        digest=digest,
        caveats=caveats_for(state.domain.operational_spec, digest.caveats),
    )
