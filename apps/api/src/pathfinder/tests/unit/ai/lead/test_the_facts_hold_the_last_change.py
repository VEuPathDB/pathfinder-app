"""The facts of a turn hold the strategy's most recent change: the change the
message found on a turn that writes nothing, and this turn's change on a turn
that writes, with the same counts as the result before and after its edit."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.last_change import LastChange
from pathfinder.domain.reply_references import prose_faults, render_reply
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SIGNAL_PEPTIDE = "Predicted Signal Peptide"
_DELETED = LastChange(before=17, after=68, what=f"deleted {_SIGNAL_PEPTIDE}")
_ASKED = "[last_change:before] before the delete and [last_change:after] after."
_TEXT = StrategyStepNode(id="step_text", search_name="GenesByText")
_JOINED = StrategyStepNode(
    id="step_join",
    search_name=COMBINE_SEARCH_NAME,
    operator=CombineOp.INTERSECT,
    primary_input=_TEXT,
    secondary_input=StrategyStepNode(
        id="step_sp", search_name="GenesWithSignalPeptide", display_name=_SIGNAL_PEPTIDE
    ),
)
_JOINED_COUNTS = {"step_text": 68, "step_sp": 431, "step_join": 17}


def _deps(root: StrategyStepNode, counts: dict[str, int]) -> LeadDeps:
    graph = StrategyGraph(graph_id="g1", name="secreted", site_id="amoebadb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session = StrategySession(site_id="amoebadb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts=dict(counts))
    state = pipeline_state(
        "amoebadb", user_message_id=uuid4(), domain=StrategyDomainState()
    )
    return lead_deps(state, strategy_session=session)


def _after_the_delete() -> LeadDeps:
    """The turn after the delete: the message found the text search alone."""
    deps = _deps(_TEXT, {"step_text": 68})
    found = StrategyAst(
        record_type="transcript", root=_TEXT, step_counts={"step_text": 68}
    )
    deps.state.turn_markers.record_change_at_arrival(found, _DELETED)
    return deps


def _deleting() -> LeadDeps:
    """The turn that deletes the signal peptide step from the joined strategy."""
    deps = _deps(_TEXT, {"step_text": 68})
    markers = deps.state.turn_markers
    markers.record_arrival("step_join", _JOINED_COUNTS)
    joined = StrategyAst(
        record_type="transcript", root=_JOINED, step_counts=_JOINED_COUNTS
    )
    markers.record_change_at_arrival(
        joined, LastChange(before=None, after=17, what="built the strategy")
    )
    markers.edited = True
    return deps


def test_a_turn_after_the_change_holds_its_counts() -> None:
    facts = turn_facts(_after_the_delete())

    assert facts.last_change == _DELETED
    assert (
        "Last change: deleted Predicted Signal Peptide; 17 genes before, 68 genes after"
        in facts.lines()
    )


def test_a_reply_names_the_count_before_an_earlier_turn_s_change() -> None:
    facts = turn_record(run_context_for(_after_the_delete())).facts

    assert prose_faults(_ASKED, facts) == []
    assert (
        render_reply(_ASKED, facts) == "17 genes before the delete and 68 genes after."
    )


def test_a_turn_that_changes_the_strategy_holds_its_own_change() -> None:
    facts = turn_facts(_deleting())

    assert facts.last_change == _DELETED
    assert (facts.root_count_before, facts.root_count) == (17, 68)


def test_a_change_written_once_per_message_is_kept() -> None:
    deps = _after_the_delete()
    deps.state.turn_markers.record_change_at_arrival(None, None)

    assert turn_facts(deps).last_change == _DELETED


def test_a_turn_that_recorded_no_arrival_states_no_change() -> None:
    assert [turn_facts(_deps(_TEXT, {"step_text": 68})).last_change] == [None]


def test_a_turn_that_builds_the_first_strategy_holds_the_build() -> None:
    deps = _deps(_TEXT, {"step_text": 68})
    deps.state.turn_markers.record_change_at_arrival(None, None)
    deps.state.turn_markers.built = True

    assert turn_facts(deps).last_change == LastChange(
        before=None, after=68, what="built the strategy"
    )
