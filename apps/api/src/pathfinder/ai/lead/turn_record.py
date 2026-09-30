"""What the turn did, as the Lead's reply must account for it."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai import RunContext

from pathfinder.ai.graph.turn_records import CreatedControlSet
from pathfinder.ai.lead.contract_messages import (
    altered_record_text_message,
    fact_outside_the_block_message,
    misattributed_source_message,
)
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.facts_in_prose import (
    altered_record_text,
    misattributed_source,
    outside_the_facts,
)
from pathfinder.ai.lead.intent import NamedControls, RefusedClassification
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


# The line of the held facts that holds the turn's counts and their differences.
_HELD_COUNTS = "Counts of this turn and their differences: "


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
    # What the turn shows beside its reply, and the names the product uses and
    # never shows: the search url segments and the step and criterion ids.
    facts: TurnFacts = TurnFacts()
    machine_names: frozenset[str] = frozenset()
    # Every line the thread's facts parts held, the researcher's own messages,
    # and the labels a comparison of this turn returned. The reply may restate
    # any of them.
    facts_shown: tuple[str, ...] = ()
    said: tuple[str, ...] = ()
    compared: tuple[str, ...] = ()
    # The counts this turn's facts show and its comparisons returned.
    counts: frozenset[int] = frozenset()
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

    def prose_refusal(self, prose: str, offered: Sequence[str]) -> str | None:
        """Why the prose holds a fact the facts do not, or None. ``offered``
        holds the options the reply's questions offer."""
        held = "\n".join([self.held_facts(), *offered])
        found = outside_the_facts(prose, held, self.machine_names)
        if found:
            return fact_outside_the_block_message(found)
        source = misattributed_source(prose, self.facts)
        if source is not None:
            return misattributed_source_message(source)
        altered = altered_record_text(prose, self.facts)
        return altered_record_text_message(altered) if altered else None

    def held_counts(self) -> frozenset[int]:
        """The turn's counts and the difference of every two of them."""
        return self.counts | {abs(a - b) for a, b in combinations(self.counts, 2)}

    def held_facts(self) -> str:
        """Every fact the reply may hold: what the thread's facts parts and this
        turn's show, what the researcher wrote, and the turn's held counts."""
        counts = ", ".join(str(n) for n in sorted(self.held_counts()))
        return "\n".join(
            [
                *self.facts_shown,
                *self.facts.held_lines(),
                *self.said,
                *self.compared,
                f"{_HELD_COUNTS}{counts}",
            ]
        )


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


def _machine_names(deps: LeadDeps) -> frozenset[str]:
    """The search url segments and the step and criterion ids of the strategy
    and its spec, which the product uses and never shows."""
    spec = deps.state.domain.operational_spec
    graph = deps.runtime.strategy_session.get_graph(None)
    criteria = [] if spec is None else spec.criteria
    steps = [] if graph is None else list(graph.steps.values())
    return frozenset(
        name
        for name in (
            *(c.id for c in criteria),
            *(c.search_name for c in criteria),
            *(step.id for step in steps),
            *(step.search_name or "" for step in steps),
        )
        if name
    )


def turn_record(ctx: RunContext[LeadDeps]) -> TurnRecord:
    """Everything the contract reads about the turn this reply answers."""
    deps = ctx.deps
    markers = deps.state.turn_markers
    classified = turn_is_classified(deps)
    ledger = derive_ledger(deps.state, deps.intent)
    facts = turn_facts(deps, refusal=markers.unbound_edit)
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
        facts=facts,
        machine_names=_machine_names(deps),
        facts_shown=tuple(deps.state.domain.facts_shown),
        said=tuple(deps.state.researcher_messages()),
        compared=tuple(markers.compared_labels),
        counts=facts.counts() | frozenset(markers.compared_counts),
        frame_open_questions=_frame_open_questions(deps, ledger.frame),
        answered_a_card=markers.consulted or markers.accepted_proposal,
        refused_classification=None if classified else deps.refused_classification,
        resumes_parked_call=deps.state.resumes_parked_call,
        named_controls=deps.intent.named_controls
        if classified and deps.intent is not None
        else None,
    )
