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
)
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    StepPushFailure,
)
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintSource,
    merge_constraints,
    provisional_constraints,
)

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

    No I/O. The Lead calls this on every turn. Sub-agents do NOT call it —
    they receive scoped slices via typed work orders from the Lead.

    ``phase_stop`` is why the turn's last dispatch ended without a delta. It
    lives for one turn, so the caller holding it passes it in.
    """
    return InvestigationLedger(
        user_intent=intent,
        frame=FrameSection(
            spec=state.domain.operational_spec,
            spec_before_turn=state.domain.spec_before_turn,
        ),
        build=_derive_build_section(state),
        verification=_derive_verification_section(state),
        constraints=_derive_constraint_section(state, intent),
        phase_stop=phase_stop,
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


def _derive_constraint_section(
    state: PipelineState, intent: UserIntent | None
) -> ConstraintSection:
    spec = state.domain.operational_spec
    provisional = list(spec.constraints) if spec else []
    requirements = _thread_requirements(state, intent)
    merged = merge_constraints(provisional, requirements)
    kept = {(c.kind, c.requested_value) for c in merged}
    merged.extend(c for c in requirements if (c.kind, c.requested_value) not in kept)
    recommended = list(state.domain.recommendations)
    composed = [
        c for c in requirements if c.source is not ConstraintSource.USER_EXPLICIT
    ]
    carried = _carried_requirements(state, intent)
    assumed = assumption_constraints(spec)
    if not merged:
        return ConstraintSection(
            grounded=assumed,
            recommended=recommended,
            carried=carried,
            composed=composed,
        )
    if spec is None:
        return ConstraintSection(
            grounded=provisional_constraints(merged),
            recommended=recommended,
            carried=carried,
            composed=composed,
        )
    return ConstraintSection(
        grounded=[
            *ground_against_spec(merged, spec),
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
    return VerificationSection(digest=state.domain.verification_digest)
