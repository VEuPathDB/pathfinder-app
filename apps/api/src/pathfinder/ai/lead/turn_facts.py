"""The facts part of a turn, read from the strategy, the spec and the ledger."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from veupathdb.domain.strategy import StrategyStep

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.facts_reads import (
    listed_ids,
    named_genes,
    read_sources,
    saved_sets,
    with_counts_before,
)
from pathfinder.ai.lead.intent_gate import turn_is_an_audit
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.ledger_sections import unexpressed_words
from pathfinder.ai.lead.parameter_facts import step_parameters
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.tally_steps import tallies_with_paths
from pathfinder.ai.lead.unsaved_set import result_not_saved
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.caveats import (
    EditDirectionCaveat,
    Gap,
    WordGap,
    caveats_for,
    check_gaps,
    edit_direction_caveats,
)
from pathfinder.domain.control_result_facts import control_result_fact
from pathfinder.domain.gene_homes import gene_record_class
from pathfinder.domain.last_change import LastChange, change_since
from pathfinder.domain.organism_caveat import RecordsOrganismCaveat
from pathfinder.domain.read_facts import read_fact
from pathfinder.domain.site_checks import SiteCheckGap
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.expression_handles import held_readings
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.option_labels import with_readings
from pathfinder.domain.strategy.record_class_check import step_class_of
from pathfinder.domain.strategy.requirement_lifecycle import RetiredRequirement
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.domain.turn_facts import (
    UNCHECKED_PROSE,
    UNVERIFIED_BUILD,
    RetiredFact,
    StepFact,
    StrategyLinkFact,
    TurnFacts,
)
from pathfinder.domain.zero_combine import zero_combine_caveats
from pathfinder.services.gene_sets.homes import site_kind
from pathfinder.services.strategies.commit import live_strategy_url


def _strategy_link(
    site_id: str, sync: SyncStateProtocol | None
) -> StrategyLinkFact | None:
    url = live_strategy_url(site_id, sync)
    return None if url is None else StrategyLinkFact(site_id=site_id, url=url)


def _reason(criterion: Criterion | None) -> str:
    if criterion is None or criterion.rationale is None:
        return ""
    return criterion.rationale.facts_line()


def _considered(criterion: Criterion | None) -> list[str]:
    if criterion is None or criterion.rationale is None:
        return []
    return criterion.rationale.considered()


def _step_fact(
    step: StrategyStep,
    criteria: Mapping[str, Criterion],
    counts: Mapping[str, int | None],
    errors: Mapping[str, str],
    noun: str,
    said: Sequence[str],
) -> StepFact:
    criterion = criteria.get(step.id)
    named = step.display_name or (
        criterion.search_display_name if criterion is not None else None
    )
    return StepFact(
        step_id=step.id,
        display_name=named or step.display_label,
        operator=None if step.operator is None else step.operator.value,
        count=counts.get(step.id),
        reason=_reason(criterion),
        also_considered=_considered(criterion),
        parameters=[] if criterion is None else step_parameters(criterion, noun, said),
        error=errors.get(step.id, ""),
        record_noun=noun,
    )


def _built_steps(
    graph: StrategyGraph | None,
    spec: OperationalSpec | None,
    sync: SyncStateProtocol | None,
    outcome: BuildOutcome | None,
    said: Sequence[str],
) -> list[StepFact]:
    """The steps under the strategy's root, each after the inputs it reads.

    ``said`` holds the researcher's messages, which state an analysis value.
    """
    root_id = None if graph is None else graph.primary_root_id()
    if graph is None or root_id is None:
        return []
    criteria = {} if spec is None else {c.id: c for c in spec.criteria}
    counts = {} if sync is None else dict(sync.step_counts)
    errors = (
        {}
        if outcome is None
        else {n.node_id: n.error for n in outcome.node_results if n.error}
    )
    record_types = _record_types(graph)
    return [
        _step_fact(
            step, criteria, counts, errors, counted_noun(record_types[step.id]), said
        )
        for step in graph.steps_in_tree_order(root_id)
    ]


def _record_types(graph: StrategyGraph | None) -> dict[str, str | None]:
    if graph is None:
        return {}
    return {step_id: step_class_of(graph.steps, step_id) for step_id in graph.steps}


def _counted_live(
    spec: OperationalSpec | None,
    sync: SyncStateProtocol | None,
    readings: Mapping[str, str],
) -> OperationalSpec | None:
    """The spec with each bind count that did not arrive taken from the live
    strategy's count of the step it built, and each built expression read."""
    if spec is not None and sync is not None:
        spec = spec.counted_at(sync.step_counts)
    return with_readings(spec, readings)


def _draft_steps(spec: OperationalSpec | None, said: Sequence[str]) -> list[StepFact]:
    """The bound criteria of a spec nothing is built from yet."""
    if spec is None:
        return []
    noun = counted_noun(spec.record_type)
    return [
        StepFact(
            step_id=c.id,
            display_name=c.search_display_name or c.text,
            count=c.result_count,
            reason=_reason(c),
            also_considered=_considered(c),
            parameters=step_parameters(c, noun, said),
            record_noun=noun,
        )
        for c in spec.criteria
        if c.bound
    ]


def _retired(
    retired: RetiredRequirement, words: Mapping[str, str]
) -> list[RetiredFact]:
    """The rows of the retired requirement, and the one that replaced it, in
    the words the researcher stated each in; ``words`` holds them by key."""
    lifecycle = retired.lifecycle
    return [
        RetiredFact(
            requirement=shown,
            state=lifecycle.state,
            replaced_by=""
            if lifecycle.state == "withdrawn"
            else words.get(lifecycle.by, lifecycle.by),
        )
        for shown in retired.shown_requirements()
    ]


def _retired_rows(domain: StrategyDomainState) -> list[RetiredFact]:
    words = {
        c.key: c.requested_value
        for c in [
            *domain.requirements,
            *(r.constraint for r in domain.retired_requirements),
        ]
    }
    return [row for r in domain.retired_requirements for row in _retired(r, words)]


def _gaps(deps: LeadDeps, ledger: InvestigationLedger) -> list[Gap]:
    """The gaps of the verdict on the strategy, and on a turn that framed or
    changed it, every word its spec states and every requirement the framing
    pass found no search states, read again against every requirement so a
    withdrawn or replaced one is no gap."""
    markers = deps.state.turn_markers
    verdict = deps.state.turn_verdict
    held = [] if verdict is None else verdict.gaps
    retired = {r.constraint.key for r in deps.state.domain.retired_requirements}
    words = [
        *(gap.word for gap in held if isinstance(gap, WordGap)),
        *(
            unexpressed_words(deps.state.domain.operational_spec)
            if markers.framed or markers.changed_strategy
            else []
        ),
    ]
    return [
        *check_gaps(
            words=words,
            unstated=markers.unstated_requirements,
            requirements=[
                *ledger.constraints.grounded,
                *(r.grounded() for r in deps.state.domain.retired_requirements),
            ],
        ),
        *(
            gap
            for gap in held
            if isinstance(gap, SiteCheckGap) and gap.check.requirement not in retired
        ),
    ]


def _moved_against_the_edit(
    deps: LeadDeps, built: list[StepFact], noun: str
) -> list[EditDirectionCaveat]:
    """Each step this turn's writes moved against the way it was asked to."""
    return edit_direction_caveats(
        "other" if deps.intent is None else deps.intent.edit_direction,
        {s.step_id: s.count_before for s in built if s.count_before is not None},
        {step.step_id: (step.display_name, step.count) for step in built},
        noun,
    )


def _last_change(deps: LeadDeps, graph: StrategyGraph | None) -> LastChange | None:
    """The change the message found, or the one this turn made since. A turn
    that recorded nothing at arrival states no change."""
    found = deps.state.turn_markers.change_at_arrival
    if found is None:
        return None
    sync = deps.runtime.strategy_session.sync_state
    return change_since(
        found.tree,
        found.change,
        None if graph is None else graph.to_strategy_ast(sync_state=sync),
    )


def _records_organism(deps: LeadDeps) -> list[RecordsOrganismCaveat]:
    outcome = deps.state.domain.last_build_outcome
    change = None if outcome is None else outcome.organism_change
    if change is None or not deps.state.turn_markers.changed_strategy:
        return []
    return [RecordsOrganismCaveat(records=change.records, seed=change.seed)]


_STATED_HEAD = 80


def _failed_check(
    deps: LeadDeps, ledger: InvestigationLedger, gaps: Sequence[Gap]
) -> str:
    digest = ledger.verification.digest
    if digest is None or digest.success or turn_is_an_audit(deps):
        return ""
    head = digest.reason[:_STATED_HEAD]
    if not head or any(head in gap.sentence for gap in gaps):
        return "The last check of this strategy failed."
    return f"The last check of this strategy failed: {digest.reason}"


def turn_facts(deps: LeadDeps, *, refusal: str = "") -> TurnFacts:
    """Everything this turn shows beside its reply.

    ``refusal`` is the provider's or the site's refusal that ended the turn,
    whole.
    """
    state = deps.state
    markers = state.turn_markers
    domain = state.domain
    session = deps.runtime.strategy_session
    readings = held_readings(domain.built_expressions)
    spec = _counted_live(domain.operational_spec, session.sync_state, readings)
    # A built step runs the values the strategy answers to; a draft a pass
    # bound and no push wrote is the plan, not the step.
    answered = _counted_live(domain.answered_spec, session.sync_state, readings)
    graph = session.get_graph(None)
    ledger = derive_ledger(state, deps.intent)
    said = state.researcher_messages()
    built = with_counts_before(
        _built_steps(graph, answered, session.sync_state, ledger.build.outcome, said),
        markers,
    )
    verdict = state.turn_verdict
    stop = deps.last_phase_stop
    genes = gene_record_class(site_kind(deps.runtime.site_id))
    noun = counted_noun(graph.record_type if graph and graph.steps else genes)
    sources = read_sources(
        markers,
        built,
        session.sync_state,
        None if verdict is None else verdict.review,
    )
    gaps = _gaps(deps, ledger)
    return TurnFacts(
        request_messages=said,
        record_noun=noun,
        steps=built or _draft_steps(spec, said),
        draft=not built,
        root_count=built[-1].count if built else None,
        root_count_before=markers.root_count_before() if built else None,
        last_change=_last_change(deps, graph),
        removed=[step.title for step in markers.deleted_steps],
        strategy_link=_strategy_link(deps.runtime.site_id, session.sync_state)
        if built
        else None,
        caveats=[
            *caveats_for(spec, [] if verdict is None else verdict.caveats),
            *_moved_against_the_edit(deps, built, noun),
            *_records_organism(deps),
            *(
                []
                if graph is None or session.sync_state is None
                else zero_combine_caveats(
                    graph.steps, session.sync_state.step_counts, noun
                )
            ),
        ],
        gaps=gaps,
        column_fits=[] if verdict is None else list(verdict.review.column_fits),
        retired=_retired_rows(domain),
        saved=saved_sets(markers, genes),
        unsaved=result_not_saved(deps.runtime.site_id, graph, session.sync_state)
        if markers.changed_strategy
        else None,
        control_results=[
            control_result_fact(run.evidence) for run in markers.control_tests
        ],
        sources=sources,
        listed=listed_ids(
            deps.runtime.site_id,
            markers,
            built,
            session.sync_state,
            sources,
            _record_types(graph),
        ),
        named_genes=named_genes(markers),
        shown_before=list(domain.shown_records),
        comparisons=list(markers.comparisons),
        memberships=list(markers.memberships),
        statistics=list(domain.statistics),
        reads=[
            read_fact(fact)
            for fact in (
                *markers.audit_facts,
                *(held.fact() for held in domain.computed_comparisons.values()),
            )
        ],
        tallies=tallies_with_paths(session, markers.tallies),
        result_step_id=None
        if not built or session.sync_state is None
        else session.sync_state.wdk_root_step_id,
        stopped_check=""
        if stop is None or stop.role != "verification"
        else stop.render(),
        failed_check=_failed_check(deps, ledger, gaps),
        refusal=refusal,
        unchecked=UNCHECKED_PROSE if markers.unchecked_reply else "",
        unverified=UNVERIFIED_BUILD if deps.build_unverified else "",
    )


__all__ = ["turn_facts"]
