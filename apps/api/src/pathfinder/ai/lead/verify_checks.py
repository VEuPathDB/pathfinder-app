from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic_ai import ToolFailed
from veupathdb.domain.strategy import StepKind, StrategyStep
from veupathdb.wdk import WDKStep, WDKStrategyDetails, encode_params
from veupathdb_mcp.wdk import MAX_COLUMN_COUNT_TOP

from pathfinder.ai.capabilities.site_reads import read_in_time
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.derive import grounded_requirements
from pathfinder.ai.lead.evidence_card import judged_expression_fits
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.ai.tools.standalone.results import (
    READ_DEADLINE_SECONDS,
    read_step_columns,
)
from pathfinder.domain.requirement_checks import (
    classes_named,
    grounded_check,
    record_type_check,
)
from pathfinder.domain.site_checks import (
    CountedOrganisms,
    HeldValue,
    JoinedCounts,
    OrganismCount,
    SiteCheck,
    SiteStep,
    UnreadOrganisms,
    bound_values_check,
    combine_counts_check,
    expression_fit_checks,
    organism_check,
    result_count_check,
    tally_checks,
    unanswered_checks,
    unanswered_columns,
    validity_check,
)
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    ConstraintSource,
    GroundedConstraint,
)
from pathfinder.domain.strategy.organism_phrases import names_the_organism
from pathfinder.domain.strategy.organism_scope import (
    dataset_organisms_of,
    organism_params_of,
    output_organisms,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.services.eda.analysis_kinds import read_the_unread_kinds
from pathfinder.services.experiment.column_tally import ColumnTallyRefusedError
from pathfinder.services.experiment.paged_tally import (
    GENOME_COLUMN,
    PAGED_RECORDS,
    count_paged_values,
)
from pathfinder.services.experiment.reporter_refusals import ReporterRefusedError
from pathfinder.services.experiment.step_tally import CountedStep, run_step_tally
from pathfinder.services.site_errors import answered_with_a_status
from pathfinder.services.strategies.record_classes import names_of_every_record_type
from pathfinder.services.strategies.site_changes import (
    values_the_site_holds_otherwise,
)
from pathfinder.services.strategies.site_counts import read_site_strategy

_ORGANISM_COLUMN = "organism"
_RESULT_ORGANISMS = "the organisms of the result"


@dataclass(frozen=True)
class _Judged:
    site_id: str
    graph: StrategyGraph
    held: Mapping[str, WDKStep]
    steps: Mapping[str, SiteStep]

    def count(self, step_id: str | None) -> int | None:
        step = None if step_id is None else self.steps.get(step_id)
        return None if step is None else step.count

    @property
    def root(self) -> SiteStep | None:
        root_id = self.graph.primary_root_id()
        return None if root_id is None else self.steps.get(root_id)


def _judged(
    site_id: str,
    graph: StrategyGraph,
    sync: SyncStateProtocol,
    details: WDKStrategyDetails,
) -> _Judged:
    held = {
        step_id: site
        for step_id, wdk_step_id in sync.wdk_step_ids.items()
        if step_id in graph.steps
        and (site := details.steps.get(str(wdk_step_id))) is not None
    }
    steps = {
        step_id: SiteStep(
            title=graph.steps[step_id].display_label,
            wdk_step_id=site.id,
            count=site.estimated_size,
            record_class=site.record_class_name,
            validation=site.validation,
        )
        for step_id, site in held.items()
    }
    return _Judged(site_id=site_id, graph=graph, held=held, steps=steps)


async def _bound_values(judged: _Judged) -> SiteCheck:
    differing: list[HeldValue] = []
    compared = 0
    for step_id, site in judged.held.items():
        step = judged.graph.steps[step_id]
        if step.kind is StepKind.COMBINE or not step.parameters:
            continue
        compared += 1
        bound = encode_params(step.parameters)
        moved = await values_the_site_holds_otherwise(step, site, judged.site_id)
        differing.extend(
            HeldValue(
                step=judged.steps[step_id].named,
                param=name,
                bound=bound[name],
                site=value,
            )
            for name, value in moved.items()
        )
    return bound_values_check(compared, differing)


def _join(judged: _Judged, step: StrategyStep) -> JoinedCounts | None:
    if step.kind is not StepKind.COMBINE or step.operator is None:
        return None
    return JoinedCounts(
        title=step.display_label,
        operator=step.operator,
        left=judged.count(step.primary_input_id),
        right=judged.count(step.secondary_input_id),
        joined=judged.count(step.id),
    )


async def _strategy_checks(judged: _Judged) -> list[SiteCheck]:
    joins = [
        join
        for step in judged.graph.steps.values()
        if step.id in judged.steps and (join := _join(judged, step)) is not None
    ]
    combined = combine_counts_check(joins)
    return [
        validity_check(list(judged.steps.values())),
        await _bound_values(judged),
        *([] if combined is None else [combined]),
        result_count_check(judged.root),
    ]


async def _counted_organisms(
    judged: _Judged, root: SiteStep
) -> CountedOrganisms | UnreadOrganisms:
    if root.count is not None and root.count <= PAGED_RECORDS:
        return await _paged_organisms(judged, root)
    counted = CountedStep(
        site_id=judged.site_id,
        wdk_step_id=root.wdk_step_id,
        record_type=root.record_class or "",
        search_name="",
        record_noun=counted_noun(root.record_class),
        step_url=None,
    )
    try:
        tally = await read_in_time(
            "the organism count",
            root.named,
            run_step_tally(counted, _ORGANISM_COLUMN, MAX_COLUMN_COUNT_TOP),
            deadline=READ_DEADLINE_SECONDS,
        )
    except ReporterRefusedError:
        return _refused_organisms(root)
    except ColumnTallyRefusedError as refused:
        return UnreadOrganisms(
            why="no_check",
            evidence=f"the site does not count the organisms of {root.named}: {refused}",
        )
    except ToolFailed:
        return _unanswered_organisms(root)
    rows = [OrganismCount(organism=row.value, count=row.count) for row in tally.rows]
    return CountedOrganisms(step=root.named, total=tally.total, rows=rows)


def _refused_organisms(root: SiteStep) -> UnreadOrganisms:
    return UnreadOrganisms(
        why="site_refused",
        evidence=f"the site refused the organism count of {root.named}",
    )


def _unanswered_organisms(root: SiteStep) -> UnreadOrganisms:
    return UnreadOrganisms(
        why="site_unanswered",
        evidence=f"the site did not answer the organism count of {root.named}",
    )


async def _paged_organisms(
    judged: _Judged, root: SiteStep
) -> CountedOrganisms | UnreadOrganisms:
    try:
        paged = await read_in_time(
            "the organism count",
            root.named,
            count_paged_values(
                judged.site_id, root.wdk_step_id, root.record_class, GENOME_COLUMN
            ),
            deadline=READ_DEADLINE_SECONDS,
        )
    except ToolFailed as failed:
        if answered_with_a_status(failed.__cause__):
            return _refused_organisms(root)
        return _unanswered_organisms(root)
    rows = [
        OrganismCount(organism=organism, count=count)
        for organism, count in paged.counts.most_common()
    ]
    return CountedOrganisms(step=root.named, total=paged.total, rows=rows)


async def _organism_checks(
    deps: LeadDeps, judged: _Judged, asked: list[GroundedConstraint]
) -> list[SiteCheck]:
    spec = deps.state.domain.operational_spec
    ast = judged.graph.to_strategy_ast()
    root = judged.root
    if spec is None or ast is None or root is None:
        return []
    found = output_organisms(
        ast.root, organism_params_of(spec.criteria), dataset_organisms_of(spec.criteria)
    )
    selected = None if found is None else frozenset(found)
    counted = None if selected is None else await _counted_organisms(judged, root)
    checks: list[SiteCheck] = []
    carried = False
    for held in asked:
        c = held.constraint
        names = selected is not None and any(
            names_the_organism(c.requested_value, organism) for organism in selected
        )
        carried = carried or names
        checks.append(
            organism_check(c.requested_value, c.key, selected, counted)
            if names
            else SiteCheck(
                kind=ConstraintKind.ORGANISM,
                subject=c.requested_value,
                status="unchecked",
                evidence="no organism the strategy selects for its result is named so",
                requirement=c.key,
                why_unchecked="no_check",
            )
        )
    if not carried:
        checks.append(organism_check(_RESULT_ORGANISMS, "", selected, counted))
    return checks


async def _requirement_checks(
    deps: LeadDeps, judged: _Judged, stated: list[GroundedConstraint]
) -> list[SiteCheck]:
    names = await names_of_every_record_type(judged.site_id)
    root = judged.root
    classes = {s.record_class for s in judged.steps.values() if s.record_class}
    roles = deps.state.domain.record_roles
    return [
        record_type_check(
            held.constraint,
            roles.get(held.constraint.key, "answer"),
            classes_named(held.constraint.requested_value, names),
            None if root is None else root.record_class,
            classes,
        )
        if held.constraint.kind is ConstraintKind.RECORD_TYPE
        else grounded_check(held)
        for held in stated
        if held.constraint.kind is not ConstraintKind.ORGANISM
    ]


@dataclass(frozen=True)
class ColumnReads:
    notes: list[str]
    unanswered: list[SiteCheck]


async def read_the_columns(deps: LeadDeps, agent_deps: AgentDeps) -> ColumnReads:
    session = deps.runtime.strategy_session
    graph, sync = session.get_graph(None), session.sync_state
    reads = ColumnReads(notes=[], unanswered=[])
    if graph is None or sync is None:
        return reads
    for step_id, step in graph.steps.items():
        wdk_step_id = sync.wdk_step_ids.get(step_id)
        if step.kind is StepKind.COMBINE or not step.search_name or wdk_step_id is None:
            continue
        try:
            read = await read_step_columns(agent_deps, wdk_step_id)
        except ToolFailed:
            reads.unanswered.append(unanswered_columns(f"step {wdk_step_id}"))
            continue
        reads.notes.extend([read.note] if read.note else [])
    return reads


async def site_checks(deps: LeadDeps) -> list[SiteCheck]:
    session = deps.runtime.strategy_session
    graph, sync = session.get_graph(None), session.sync_state
    if graph is None or sync is None or sync.wdk_strategy_id is None:
        return []
    site_id = deps.runtime.site_id
    await read_the_unread_kinds(site_id=site_id, graph=graph)
    live = list(sync.wdk_step_ids.values())
    computed = [
        *expression_fit_checks(judged_expression_fits(deps)),
        *tally_checks(deps.state.turn_markers.tallies, live),
    ]
    details = await read_site_strategy(site_id, sync.wdk_strategy_id)
    if details is None:
        return [
            *unanswered_checks("the site did not answer the strategy read"),
            *computed,
        ]
    judged = _judged(site_id, graph, sync, details)
    stated = [
        held
        for held in grounded_requirements(deps.state, deps.intent)
        if held.constraint.source is ConstraintSource.USER_EXPLICIT
    ]
    asked = [h for h in stated if h.constraint.kind is ConstraintKind.ORGANISM]
    return [
        *await _strategy_checks(judged),
        *await _requirement_checks(deps, judged, stated),
        *await _organism_checks(deps, judged, asked),
        *computed,
    ]


__all__ = ["ColumnReads", "read_the_columns", "site_checks"]
