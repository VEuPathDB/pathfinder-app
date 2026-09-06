from __future__ import annotations

from veupathdb.domain.parameters.value_codec import to_wire
from veupathdb.domain.strategy.build_outcome import (
    BuildOutcome,
    StepPushFailure,
)
from veupathdb.domain.strategy.constraints import (
    Constraint,
    ConstraintSource,
    merge_constraints,
    provisional_constraints,
)

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
from pathfinder.domain.strategy.constraint_grounding import ground_constraints

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


def _derive_constraint_section(
    state: PipelineState, intent: UserIntent | None
) -> ConstraintSection:
    spec = state.domain.operational_spec
    provisional = list(spec.constraints) if spec else []
    requirements = _thread_requirements(state, intent)
    merged = merge_constraints(provisional, requirements)
    kept = {(c.kind, c.requested_value) for c in merged}
    merged.extend(
        c.model_copy(update={"source": ConstraintSource.USER_EXPLICIT})
        for c in requirements
        if (c.kind, c.requested_value) not in kept
    )
    assumed = assumption_constraints(spec)
    if not merged:
        return ConstraintSection(grounded=assumed)
    if spec is None:
        return ConstraintSection(grounded=provisional_constraints(merged))
    search_names = [c.search_name for c in spec.criteria if c.search_name]
    param_names: set[str] = {p for c in spec.criteria for p in c.resolved_params}
    param_names |= {s.param_name for c in spec.criteria for s in c.open_params}
    param_names |= {s.param_name for s in spec.open_slots}
    param_values = {
        name: to_wire(value)
        for c in spec.criteria
        for name, value in c.resolved_params.items()
    }
    return ConstraintSection(
        grounded=[
            *ground_constraints(
                merged,
                search_names=search_names,
                param_names=param_names,
                param_values=param_values,
                structure=spec.structure,
                criteria=spec.criteria,
            ),
            *assumed,
        ]
    )


def _derive_build_section(state: PipelineState) -> BuildSection:
    outcome = state.domain.last_build_outcome
    if outcome is None:
        return BuildSection(stale_build=state.domain.stale_build)
    failed_count = len(outcome.failed_steps)
    skipped_count = len(outcome.skipped_step_ids)
    zero_steps = list(outcome.zero_step_ids)
    needs_recovery = bool(failed_count or skipped_count or zero_steps)
    return BuildSection(
        outcome=outcome,
        stale_build=state.domain.stale_build,
        pushed_count=len(outcome.pushed_step_ids),
        failed_count=failed_count,
        skipped_count=skipped_count,
        zero_result_steps=zero_steps,
        needs_recovery=needs_recovery,
        recovery_kind=_recovery_kind(outcome),
    )


def _recovery_kind(outcome: BuildOutcome) -> RecoveryKind:
    if not outcome.failed_steps and not outcome.skipped_step_ids:
        if outcome.zero_step_ids:
            return "empty_result_review"
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
