"""What the turn did, as the Lead's reply must account for it."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai import RunContext

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.turn_records import CreatedControlSet, NamedStep
from pathfinder.ai.lead.deleted_steps import named_step
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.evidence_claims import backing_results
from pathfinder.ai.lead.intent_gate import (
    tools_the_turn_offers,
    turn_builds,
    turn_is_off_topic,
)
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    VerificationSection,
    unexpressed_words,
)
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.ai.lead.proposal import OFFER_TOOLS
from pathfinder.ai.lead.sub_agent_tools import TOOL_TO_PHASE_ROLE, LeadDeps
from pathfinder.domain.evidence import (
    ControlTestEvidence,
    RequirementCheck,
    SampledGene,
)
from pathfinder.domain.separation import offers_evidence
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion, pending_analyses
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.domain.strategy.step_words import AddedSearch

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
    retrieved_sources: tuple[str, ...]
    created_control_sets: tuple[CreatedControlSet, ...]
    created_gene_sets: tuple[CreatedGeneSet, ...]
    added_searches: tuple[AddedSearch, ...] = ()
    # The words the spec states that no search its framing pass read can state.
    unexpressed_qualifiers: tuple[str, ...] = ()
    # The control results a reply may cite: this turn's, the last check's and
    # the separation offers'.
    control_results: tuple[ControlTestEvidence, ...] = ()
    # The genes the last check of this strategy sampled, as its card shows them.
    sampled_genes: tuple[SampledGene, ...] = ()
    # The requirements a check of this turn found unmet or unexpressed.
    requirements_to_report: tuple[RequirementCheck, ...] = ()
    answered_a_card: bool = False
    # The reply is the one a card call carries, and the card asks its question.
    ends_on_a_card: bool = False
    # The steps this turn deleted, and the steps the strategy holds now.
    deleted_steps: tuple[NamedStep, ...] = ()
    standing_steps: tuple[NamedStep, ...] = ()
    # The strategy's record type, the count of each step it holds, and the
    # counts its steps held when the message arrived.
    record_type: str = ""
    step_counts: tuple[int, ...] = ()
    counts_at_arrival: tuple[int, ...] = ()


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


def _requirements_to_report(deps: LeadDeps) -> tuple[RequirementCheck, ...]:
    """The rows a check of this turn found unmet or unexpressed."""
    verdict = deps.state.turn_verdict
    if not deps.state.turn_markers.verification_dispatched or verdict is None:
        return ()
    return tuple(verdict.review.to_report())


def _cited_offers(deps: LeadDeps, card_offer: str | None) -> list[ControlTestEvidence]:
    """The reads of the offer on the turn's card and of the offer the thread adopted."""
    domain = deps.state.domain
    adopted = domain.attached_controls
    return offers_evidence(
        domain.separation_offers,
        [card_offer, None if adopted is None else adopted.task_id],
    )


def turn_record(
    ctx: RunContext[LeadDeps], *, card_offer: str | None = None
) -> TurnRecord:
    """Everything the contract reads about the turn this reply answers.

    ``card_offer`` is the task id of the separation offer the turn's card
    carries, or None.
    """
    deps = ctx.deps
    markers = deps.state.turn_markers
    ledger = derive_ledger(deps.state, deps.intent)
    card = deps.state.domain.card_of_the_strategy()
    graph = deps.runtime.strategy_session.get_graph(None)
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
        retrieved_sources=tuple(markers.retrieved_sources),
        created_control_sets=tuple(markers.created_control_sets),
        created_gene_sets=tuple(markers.created_gene_sets),
        added_searches=tuple(markers.added_searches),
        unexpressed_qualifiers=tuple(
            unexpressed_words(deps.state.domain.operational_spec)
        ),
        control_results=backing_results(
            (run.evidence for run in markers.control_tests),
            card,
            _cited_offers(deps, card_offer),
        ),
        sampled_genes=() if card is None else tuple(card.review.sampled_genes),
        requirements_to_report=_requirements_to_report(deps),
        answered_a_card=markers.consulted or markers.accepted_proposal,
        deleted_steps=tuple(markers.deleted_steps),
        standing_steps=()
        if graph is None
        else tuple(named_step(node) for node in graph.steps.values()),
        record_type="" if graph is None else graph.record_type or "",
        step_counts=_step_counts(deps),
        counts_at_arrival=tuple(markers.counts_at_arrival),
    )


def _step_counts(deps: LeadDeps) -> tuple[int, ...]:
    """The count of each step the strategy holds, as the site answered it."""
    sync = deps.runtime.strategy_session.sync_state
    if sync is None:
        return ()
    return tuple(count for count in sync.step_counts.values() if count is not None)
