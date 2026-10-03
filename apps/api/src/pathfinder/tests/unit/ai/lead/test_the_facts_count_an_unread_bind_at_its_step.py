"""The facts count a binding whose own count did not arrive at the count the
live strategy holds for its step, in the value row and in the caveats."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import (
    domain_answering,
    lead_deps,
    pipeline_state,
)

_STEP = "c_ortholog_agam_pest"
_SEARCH = "GenesByOrthologPattern"


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="Anopheles funestus genes with an ortholog in Anopheles gambiae PEST",
        criteria=[
            Criterion(
                id=_STEP,
                text="an ortholog in Anopheles gambiae PEST",
                search_name=_SEARCH,
                search_display_name="Orthology Phylogenetic Profile",
                resolved_params={
                    "included_species": BoundValue(
                        value=StringValue(value="agam"), source="chosen"
                    )
                },
                param_display_names={"included_species": "Included Species"},
                measurements=[
                    Measurement(
                        kind="bound_count", param="included_species", reading="agam"
                    )
                ],
            )
        ],
    )


def _session(count: int | None) -> StrategySession:
    graph = StrategyGraph(graph_id="g1", name="orthologs", site_id="vectorbase")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id=_STEP, search_name=_SEARCH))
    graph.recompute_roots()
    session = StrategySession(site_id="vectorbase")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={_STEP: count})
    return session


def _facts(count: int | None) -> tuple[list[str], list[str]]:
    state = pipeline_state("vectorbase", domain=domain_answering(_spec()))
    facts = turn_facts(lead_deps(state, strategy_session=_session(count)))
    [step] = facts.steps
    [row] = step.parameters
    return row.lines(), [
        c.sentence for c in facts.caveats if c.kind == "unmeasured_value"
    ]


def test_the_step_count_replaces_the_bind_count_that_did_not_arrive() -> None:
    assert _facts(12318) == (
        [
            "Included Species: agam",
            (
                "Included Species at the chosen agam: 12,318 genes; its other "
                "readings: not measured"
            ),
        ],
        [],
    )


def test_a_step_the_site_has_not_counted_keeps_the_bind_unread() -> None:
    """The row says the count was not measured, so no caveat says it again."""
    assert _facts(None) == (
        ["Included Species: agam", "Included Species at the chosen agam: not measured"],
        [],
    )
