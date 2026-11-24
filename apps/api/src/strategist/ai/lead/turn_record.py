"""What the turn did, as the Lead's reply must account for it."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai import RunContext

from strategist.ai.graph.turn_records import CreatedControlSet
from strategist.ai.lead.derive import derive_ledger
from strategist.ai.lead.intent import (
    NamedControls,
)
from strategist.ai.lead.intent_gate import (
    turn_builds,
    turn_is_classified,
    turn_is_off_topic,
)
from strategist.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
)
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.column_reach import StepReach
from strategist.domain.strategy.operational_spec import (
    Criterion,
)
from strategist.domain.strategy.pending_analyses import pending_analyses
from strategist.domain.turn_facts import TurnFacts


class TurnRecord(CamelModel):
    """What this turn did, as the reply must account for it."""

    model_config = ConfigDict(frozen=True)

    changed_strategy: bool
    eda_criterion_pending: Criterion | None
    eda_workflow_started: bool
    turn_builds: bool
    framed: bool
    off_topic: bool
    build_section: BuildSection
    verification_section: VerificationSection
    created_control_sets: tuple[CreatedControlSet, ...]
    # What the turn shows beside its reply.
    facts: TurnFacts = TurnFacts()
    # The values a frame pass of this turn left for the user to choose.
    frame_open_questions: tuple[str, ...] = ()
    answered_a_card: bool = False
    # The reply is the one a card call carries, and the card asks its question.
    ends_on_a_card: bool = False
    # The refusal that stands while the message holds no accepted classification.
    # The turn re-enters a call the thread parked, and answers no new message.
    resumes_parked_call: bool = False
    # The controls the accepted classification says the message names.
    named_controls: NamedControls | None = None
    unfollowed_reach: StepReach | None = None
    unmet_requirements: tuple[str, ...] = ()


def _pending_eda_criterion(deps: LeadDeps) -> Criterion | None:
    """The first criterion no step exports yet, or None."""
    return next(iter(pending_analyses(deps.state.domain.operational_spec)), None)


def owes_a_check(deps: LeadDeps) -> bool:
    """Whether the turn built steps, no check of them was dispatched, and no
    criterion of the build waits on its analysis. A turn that only deleted or
    cleared steps owes none."""
    if not deps.build_unverified or deps.state.turn_markers.verification_dispatched:
        return False
    return not (turn_builds(deps) and _pending_eda_criterion(deps) is not None)


def _eda_workflow_started(deps: LeadDeps) -> bool:
    """Whether an analysis is open on the dataset of a criterion that waits."""
    opened = set(deps.state.turn_markers.eda_datasets_opened)
    analysis = deps.state.domain.open_eda_analysis
    if analysis is not None:
        opened.add(analysis.dataset_id)
    waiting = pending_analyses(deps.state.domain.operational_spec)
    return any(criterion.needs_analysis_on in opened for criterion in waiting)


def _frame_open_questions(deps: LeadDeps, frame: FrameSection) -> tuple[str, ...]:
    """The questions a frame pass of this turn recorded, or else the open slots
    of the spec a frame pass of this turn wrote. A spec with no open slot asks
    nothing, whatever an earlier pass recorded."""
    if not frame.needs_user:
        return ()
    markers = deps.state.turn_markers
    arrived = set(markers.questions_at_arrival)
    asked = tuple(
        q.question
        for q in deps.state.domain.open_questions
        if q.question not in arrived
    )
    if asked or not markers.framed:
        return asked
    return tuple(slot.question or slot.param_name for slot in frame.open_slots())


def turn_record(ctx: RunContext[LeadDeps]) -> TurnRecord:
    """Everything the contract reads about the turn this reply answers."""
    deps = ctx.deps
    markers = deps.state.turn_markers
    classified = turn_is_classified(deps)
    ledger = derive_ledger(deps.state, deps.intent)
    return TurnRecord(
        changed_strategy=markers.changed_strategy,
        eda_criterion_pending=_pending_eda_criterion(deps),
        eda_workflow_started=_eda_workflow_started(deps),
        turn_builds=turn_builds(deps),
        framed=markers.framed,
        off_topic=turn_is_off_topic(deps),
        build_section=ledger.build,
        verification_section=ledger.verification,
        created_control_sets=tuple(markers.created_control_sets),
        facts=turn_facts(deps, refusal=markers.unbound_edit),
        frame_open_questions=_frame_open_questions(deps, ledger.frame),
        answered_a_card=markers.consulted or markers.accepted_proposal,
        resumes_parked_call=deps.state.resumes_parked_call,
        named_controls=deps.intent.named_controls
        if classified and deps.intent is not None
        else None,
        unfollowed_reach=markers.unfollowed_reach(),
        unmet_requirements=tuple(
            g.constraint.requested_value
            for g in ledger.constraints.grounded
            if g.blocks
        ),
    )
