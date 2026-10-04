"""The facts part of a turn, read from the strategy, the spec and the ledger."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from veupathdb.domain.parameters import to_wire
from veupathdb.domain.strategy import StrategyStep

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.analysis_facts import analysis_parameters
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.facts_reads import (
    listed_ids,
    named_genes,
    read_sources,
    with_counts_before,
)
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.ledger_sections import unexpressed_words
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.caveats import (
    EditDirectionCaveat,
    Gap,
    StructureGap,
    WordGap,
    caveats_for,
    check_gaps,
    edit_direction_caveats,
)
from pathfinder.domain.constraint_check import shortfalls
from pathfinder.domain.control_result_facts import control_result_fact
from pathfinder.domain.evidence import VerificationReview
from pathfinder.domain.last_change import LastChange, change_since
from pathfinder.domain.log2_scale import fold_label
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.measurement_clauses import (
    counted_clauses,
    read_pick_clauses,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import option_label
from pathfinder.domain.strategy.requirement_lifecycle import RetiredRequirement
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.domain.strategy.value_binding import plain_value
from pathfinder.domain.turn_facts import (
    ParameterFact,
    RetiredFact,
    SavedSetFact,
    StepFact,
    TurnFacts,
)
from pathfinder.domain.zero_combine import zero_combine_caveats
from pathfinder.services.strategies.commit import live_strategy_url


def _label(criterion: Criterion, param: str, bound: BoundValue) -> str:
    """The label the vocabulary gives the value, else the fold a log2 value is."""
    return bound.label or fold_label(
        criterion.display_name_of(param), plain_value(bound.value)
    )


def _notes(criterion: Criterion, param: str, bound: BoundValue, noun: str) -> list[str]:
    """The measurements of a default or chosen value, the option of a card value,
    and for every value the pick taken from a vocabulary read."""
    match bound.source:
        case "default" | "chosen":
            return counted_clauses(criterion, param, noun=noun)
        case "card":
            return [
                option_label(criterion, param, to_wire(bound.value), noun=noun),
                *read_pick_clauses(criterion, param, noun=noun),
            ]
        case _:
            return read_pick_clauses(criterion, param, noun=noun)


def _parameter(
    criterion: Criterion, name: str, bound: BoundValue, noun: str
) -> ParameterFact:
    """One bound value's row. A placeholder the site left states no value, so
    it is shown as not set and nothing measures it. A pick a message names by
    its taxon is shown as that taxon and its organism count."""
    shown = criterion.display_name_of(name)
    if bound.placeholder:
        return ParameterFact(
            name=name,
            display_name=shown,
            value="not set",
            label="site placeholder",
            source=bound.source,
        )
    value, label = (
        (bound.rounded() or plain_value(bound.value), _label(criterion, name, bound))
        if bound.taxon is None
        else (bound.taxon.name, bound.taxon.label())
    )
    return ParameterFact(
        name=name,
        display_name=shown,
        value=value,
        label=label,
        source=bound.source,
        notes=_notes(criterion, name, bound, noun),
    )


def _parameters(
    criterion: Criterion, noun: str, said: Sequence[str]
) -> list[ParameterFact]:
    if criterion.analysis is not None:
        return analysis_parameters(criterion.analysis, said, noun)
    return [
        _parameter(criterion, name, bound, noun)
        for name, bound in criterion.shown_values.items()
    ]


def _reason(criterion: Criterion | None) -> str:
    if criterion is None or criterion.rationale is None:
        return ""
    return criterion.rationale.line()


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
        parameters=[] if criterion is None else _parameters(criterion, noun, said),
        error=errors.get(step.id, ""),
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
    return [
        _step_fact(
            step, criteria, counts, errors, counted_noun(graph.record_type), said
        )
        for step in graph.steps_in_tree_order(root_id)
    ]


def _counted_live(
    spec: OperationalSpec | None, sync: SyncStateProtocol | None
) -> OperationalSpec | None:
    """The spec with each bind count that did not arrive taken from the live
    strategy's count of the step it built."""
    if spec is None or sync is None:
        return spec
    return spec.counted_at(sync.step_counts)


def _draft_steps(spec: OperationalSpec | None, said: Sequence[str]) -> list[StepFact]:
    """The bound criteria of a spec nothing is built from yet."""
    if spec is None:
        return []
    return [
        StepFact(
            step_id=c.id,
            display_name=c.search_display_name or c.text,
            count=c.result_count,
            reason=_reason(c),
            parameters=_parameters(c, counted_noun(spec.record_type), said),
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
    structure = next((gap for gap in held if isinstance(gap, StructureGap)), None)
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
            structure=structure,
            words=words,
            review=VerificationReview() if verdict is None else verdict.review,
            unstated=markers.unstated_requirements,
            asked=[q.question for q in deps.state.domain.answered_questions],
            requirements=[
                *ledger.constraints.grounded,
                *(r.grounded() for r in deps.state.domain.retired_requirements),
            ],
        ),
        *shortfalls([] if verdict is None else verdict.constraint_report),
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


def turn_facts(deps: LeadDeps, *, refusal: str = "") -> TurnFacts:
    """Everything this turn shows beside its reply.

    ``refusal`` is the provider's or the site's refusal that ended the turn,
    whole.
    """
    state = deps.state
    markers = state.turn_markers
    domain = state.domain
    session = deps.runtime.strategy_session
    spec = _counted_live(domain.operational_spec, session.sync_state)
    # A built step runs the values the strategy answers to; a draft a pass
    # bound and no push wrote is the plan, not the step.
    answered = _counted_live(domain.answered_spec, session.sync_state)
    graph = session.get_graph(None)
    ledger = derive_ledger(state, deps.intent)
    said = state.researcher_messages()
    built = with_counts_before(
        _built_steps(graph, answered, session.sync_state, ledger.build.outcome, said),
        markers,
    )
    verdict = state.turn_verdict
    stop = deps.last_phase_stop
    noun = counted_noun(graph.record_type) if graph and graph.record_type else "gene"
    sources = read_sources(
        markers,
        built,
        session.sync_state,
        None if verdict is None else verdict.review,
    )
    return TurnFacts(
        request_messages=said,
        record_noun=noun,
        steps=built or _draft_steps(spec, said),
        draft=not built,
        root_count=built[-1].count if built else None,
        root_count_before=markers.root_count_before() if built else None,
        last_change=_last_change(deps, graph),
        removed=[step.title for step in markers.deleted_steps],
        strategy_url=live_strategy_url(deps.runtime.site_id, session.sync_state)
        if built
        else None,
        caveats=[
            *caveats_for(spec, [] if verdict is None else verdict.caveats),
            *_moved_against_the_edit(deps, built, noun),
            *(
                []
                if graph is None or session.sync_state is None
                else zero_combine_caveats(
                    graph.steps, session.sync_state.step_counts, noun
                )
            ),
        ],
        gaps=_gaps(deps, ledger),
        column_fits=[] if verdict is None else list(verdict.review.column_fits),
        retired=_retired_rows(domain),
        saved=[
            *(
                SavedSetFact(kind="gene_set", name=s.name, count=s.gene_count)
                for s in markers.created_gene_sets
            ),
            *(
                SavedSetFact(kind="control_set", name=s.name)
                for s in markers.created_control_sets
            ),
        ],
        control_results=[
            control_result_fact(run.evidence) for run in markers.control_tests
        ],
        sources=sources,
        listed=listed_ids(
            deps.runtime.site_id, markers, built, session.sync_state, sources
        ),
        named_genes=named_genes(markers),
        comparisons=list(markers.comparisons),
        memberships=list(markers.memberships),
        statistics=list(domain.statistics),
        stopped_check=""
        if stop is None or stop.role != "verification"
        else stop.render(),
        refusal=refusal,
    )


__all__ = ["turn_facts"]
