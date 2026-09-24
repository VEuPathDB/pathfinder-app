"""The two facts that join the plan and the strategy, and how they are kept.

``answered_spec`` is the last spec the strategy was made to answer to, and
``answered_graph`` is the tree it held at that moment. Everything between that
tree and the tree the strategy holds now was written outside this thread, and
it is played onto the specs the turn holds.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import NamedTuple

from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.ast_diff import nodes_of
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.outside_changes import OutsideChanges, outside_changes
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_hydration import Analyses
from pathfinder.domain.strategy.spec_reconciliation import (
    spec_without_pending_analyses,
)
from pathfinder.domain.strategy.spec_replay import spec_replaying
from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.services.eda.export import exported_analysis
from pathfinder.services.strategies.sheet_params import sheet_params_for_searches

__all__ = [
    "analyses_of",
    "live_tree",
    "the_changes_written_outside",
    "the_strategy_now_answers_to",
    "the_thread_wrote_the_strategy",
]

Sheets = Mapping[str, Collection[str]]


def live_tree(graph: StrategyGraph | None) -> StrategyAst | None:
    """The tree the strategy holds now, with no WDK reading on it."""
    return None if graph is None else graph.to_strategy_ast()


def analyses_of(live: StrategyAst | None) -> dict[str, AnalysisBinding]:
    """The live steps that export an analysis, by step id, read as bindings.

    Each step is read as the kind the stored strategy records for it.
    """
    if live is None:
        return {}
    words = StepWords.of(live)
    return {
        step_id: binding
        for step_id, node in nodes_of(live).items()
        if (
            binding := exported_analysis(
                words.kind_of(step_id, node.search_name), node.parameters
            )
        )
        is not None
    }


def the_strategy_now_answers_to(
    state: PipelineState,
    spec: OperationalSpec | None,
    graph: StrategyGraph | None,
) -> None:
    """Record the spec the strategy now answers to, and the tree it holds.

    Every path that makes the strategy state what the spec says calls this: a
    build, a pushed edit, a delete, a clear, an export and a hydration. A
    criterion waiting for its analysis has no step, so no strategy answers it.
    """
    domain = state.domain
    domain.answered_spec = (
        None
        if spec is None
        else spec_without_pending_analyses(spec).model_copy(deep=True)
    )
    domain.answered_graph = live_tree(graph)


async def the_changes_written_outside(
    state: PipelineState,
    *,
    site_id: str,
    graph: StrategyGraph | None,
) -> OutsideChanges:
    """Play what was written outside this thread onto every spec the turn holds.

    The turn's own baselines move with it, so the ledger reports this turn's
    work and not the researcher's own edit.
    """
    domain = state.domain
    live = live_tree(graph)
    changes = outside_changes(domain.answered_graph, live)
    reading = _Reading(
        sheets=await _sheets_the_replay_reads(site_id, domain, changes, live),
        analyses=analyses_of(live),
    )
    # A step the answer states and the plan does not is a drop the plan
    # carries, so the plan keeps it out.
    dropped = _the_plan_leaves_out(domain)
    # A baseline is the record of a moment, so it takes what was written
    # outside it and nothing else: a step this turn added is never absorbed
    # into the record the turn is measured against.
    a_moment = dropped | _every_step_but_the_ones_added_outside(changes, live)
    domain.operational_spec = _replayed(
        domain.operational_spec, changes, live, reading, may_leave_out=dropped
    )
    domain.spec_before_turn = _replayed(
        domain.spec_before_turn, changes, live, reading, may_leave_out=a_moment
    )
    domain.spec_before_dispatch = _replayed(
        domain.spec_before_dispatch, changes, live, reading, may_leave_out=a_moment
    )
    domain.answered_spec = _replayed(domain.answered_spec, changes, live, reading)
    domain.answered_graph = live
    return changes


def _the_plan_leaves_out(domain: StrategyDomainState) -> frozenset[str]:
    """The criteria the answered spec states and the plan does not."""
    answered = domain.answered_spec
    plan = domain.operational_spec
    if answered is None or plan is None:
        return frozenset()
    return frozenset({c.id for c in answered.criteria} - {c.id for c in plan.criteria})


def _every_step_but_the_ones_added_outside(
    changes: OutsideChanges, live: StrategyAst | None
) -> frozenset[str]:
    """The live steps a record of a moment is not asked to state."""
    if live is None:
        return frozenset()
    added = {step.step_id for step in changes.added}
    return frozenset(step_id for step_id in nodes_of(live) if step_id not in added)


async def the_thread_wrote_the_strategy(
    state: PipelineState,
    *,
    site_id: str,
    graph: StrategyGraph | None,
    before: StrategyAst | None,
) -> None:
    """Take onto the spec what a pass of this thread wrote on the steps.

    The plan and the answer state what the strategy now holds, so the next
    edit does not undo it. The turn's own baselines stay where they are: this
    turn made the change, and the ledger reports it.
    """
    domain = state.domain
    live = live_tree(graph)
    changes = outside_changes(before, live)
    reading = _Reading(
        sheets=await _sheets_the_replay_reads(site_id, domain, changes, live),
        analyses=analyses_of(live),
    )
    dropped = _the_plan_leaves_out(domain)
    domain.operational_spec = _replayed(
        domain.operational_spec, changes, live, reading, may_leave_out=dropped
    )
    domain.answered_spec = _replayed(domain.answered_spec, changes, live, reading)
    domain.answered_graph = live


class _Reading(NamedTuple):
    """How the replay reads the live steps: their sheets, and their analyses."""

    sheets: Sheets
    analyses: Analyses


def _replayed(
    spec: OperationalSpec | None,
    changes: OutsideChanges,
    live: StrategyAst | None,
    reading: _Reading,
    *,
    may_leave_out: Collection[str] = (),
) -> OperationalSpec | None:
    if spec is None:
        return None
    return spec_replaying(
        spec,
        changes,
        live,
        sheet_params=reading.sheets,
        analyses=reading.analyses,
        may_leave_out=may_leave_out,
    )


def _every_spec(domain: StrategyDomainState) -> list[OperationalSpec]:
    """Every spec this turn reads, plans against or restores to."""
    held = (
        domain.operational_spec,
        domain.answered_spec,
        domain.spec_before_turn,
        domain.spec_before_dispatch,
    )
    return [spec for spec in held if spec is not None]


async def _sheets_the_replay_reads(
    site_id: str,
    domain: StrategyDomainState,
    changes: OutsideChanges,
    live: StrategyAst | None,
) -> Sheets:
    """The parameter sheets of the searches this replay states or restates.

    A turn whose strategy did not move and whose specs state every live step
    reads none of them.
    """
    if live is None:
        return {}
    nodes = nodes_of(live)
    stated = {
        criterion.id for spec in _every_spec(domain) for criterion in spec.criteria
    }
    touched = {change.step_id for change in changes.changed} | {
        node.id
        for node in nodes.values()
        if node.id not in stated and node.infer_kind() != "combine"
    }
    searches = {nodes[step_id].search_name for step_id in touched if step_id in nodes}
    if not searches:
        return {}
    return await sheet_params_for_searches(
        site_id=site_id,
        record_type=live.record_type,
        search_names=sorted(searches),
    )
