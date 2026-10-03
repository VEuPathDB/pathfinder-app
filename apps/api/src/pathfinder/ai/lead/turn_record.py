"""What the turn did, as the Lead's reply must account for it."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai import RunContext

from pathfinder.ai.graph.turn_records import CreatedControlSet
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent import (
    IntentClassification,
    NamedControls,
    RefusedClassification,
)
from pathfinder.ai.lead.intent_gate import (
    tools_the_turn_offers,
    turn_builds,
    turn_is_classified,
    turn_is_off_topic,
)
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
)
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.ai.lead.proposal import OFFER_TOOLS
from pathfinder.ai.lead.sub_agent_tools import TOOL_TO_PHASE_ROLE, LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion, pending_analyses
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.domain.turn_facts import TurnFacts

# The tools the Lead calls to do the turn's work. ``build_strategy`` runs no
# sub-agent, and an accepted offer runs an edit or a build; each is refused the
# same way the dispatches are.
DISPATCH_TOOLS: frozenset[str] = frozenset(TOOL_TO_PHASE_ROLE) | {
    "build_strategy",
    *OFFER_TOOLS,
}


class TurnRecord(CamelModel):
    """What this turn did, as the reply must account for it."""

    model_config = ConfigDict(frozen=True)

    changed_strategy: bool
    build_unverified: bool
    build_outcome: BuildOutcome | None
    eda_criterion_pending: Criterion | None
    turn_builds: bool
    framed: bool
    off_topic: bool
    last_phase_stop: PhaseStop | None
    refused_dispatches: tuple[str, ...]
    build_section: BuildSection
    verification_section: VerificationSection
    frame_diff: SpecDiff | None
    created_control_sets: tuple[CreatedControlSet, ...]
    # What the turn shows beside its reply, which the reply's references name.
    facts: TurnFacts = TurnFacts()
    # The values a frame pass of this turn left for the user to choose.
    frame_open_questions: tuple[str, ...] = ()
    answered_a_card: bool = False
    # The reply is the one a card call carries, and the card asks its question.
    ends_on_a_card: bool = False
    # The refusal that stands while the message holds no accepted classification.
    refused_classification: RefusedClassification | None = None
    # The turn re-enters a call the thread parked, and answers no new message.
    resumes_parked_call: bool = False
    # The controls the accepted classification says the message names.
    named_controls: NamedControls | None = None
    # The values an accepted edit classification takes back and states.
    withdrawn_values: tuple[str, ...] = ()
    stated_values: tuple[str, ...] = ()


def _pending_eda_criterion(deps: LeadDeps) -> Criterion | None:
    """The criterion waiting for an analysis this turn did not open, or None.

    An analysis the thread already holds open on that dataset counts: the
    filters and the export act on it.
    """
    opened = set(deps.state.turn_markers.eda_datasets_opened)
    analysis = deps.state.domain.open_eda_analysis
    if analysis is not None:
        opened.add(analysis.dataset_id)
    return next(
        (
            waiting
            for waiting in pending_analyses(deps.state.domain.operational_spec)
            if waiting.needs_analysis_on not in opened
        ),
        None,
    )


def _refused_dispatches(ctx: RunContext[LeadDeps]) -> tuple[str, ...]:
    """The dispatch tools this run refused and never ran again.

    The run drops a tool from its retry record as soon as one call of it
    returns, so what is left is work the turn asked for and never did. A tool
    this turn never offered is a name the run did not know, not work it owes.
    """
    offered = tools_the_turn_offers(ctx.deps, DISPATCH_TOOLS)
    return tuple(sorted(name for name in ctx.retries if name in offered))


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


def _edit_values(deps: LeadDeps) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The values an accepted edit classification takes back and states.

    Any other classification asks for no change to the strategy's values.
    """
    intent = deps.intent
    if not turn_is_classified(deps) or intent is None:
        return (), ()
    if intent.classification is not IntentClassification.EDIT_STRATEGY:
        return (), ()
    return (
        tuple(c.requested_value for c in intent.withdrawn),
        tuple(c.requested_value for c in intent.explicit_constraints),
    )


def turn_record(ctx: RunContext[LeadDeps]) -> TurnRecord:
    """Everything the contract reads about the turn this reply answers."""
    deps = ctx.deps
    markers = deps.state.turn_markers
    classified = turn_is_classified(deps)
    ledger = derive_ledger(deps.state, deps.intent)
    withdrawn, stated = _edit_values(deps)
    return TurnRecord(
        changed_strategy=markers.changed_strategy,
        build_unverified=markers.build_unverified,
        build_outcome=deps.state.domain.last_build_outcome,
        eda_criterion_pending=_pending_eda_criterion(deps),
        turn_builds=turn_builds(deps),
        framed=markers.framed,
        off_topic=turn_is_off_topic(deps),
        last_phase_stop=deps.last_phase_stop,
        refused_dispatches=_refused_dispatches(ctx),
        build_section=ledger.build,
        verification_section=ledger.verification,
        frame_diff=ledger.frame.spec_diff(),
        created_control_sets=tuple(markers.created_control_sets),
        facts=turn_facts(deps, refusal=markers.unbound_edit),
        frame_open_questions=_frame_open_questions(deps, ledger.frame),
        answered_a_card=markers.consulted or markers.accepted_proposal,
        refused_classification=None if classified else deps.refused_classification,
        resumes_parked_call=deps.state.resumes_parked_call,
        named_controls=deps.intent.named_controls
        if classified and deps.intent is not None
        else None,
        withdrawn_values=withdrawn,
        stated_values=stated,
    )
