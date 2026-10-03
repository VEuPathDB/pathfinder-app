"""A built step's rows show the values the strategy answers to. A draft a pass
bound and no push wrote is not what the step runs."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SEARCH = "GenesByMicroarraytgonME49_microarrayExpression_White_GSE16037_Tz-Bz_RSRC"
_REF = "samples_fc_ref_generic"


def _spec(reference: str) -> OperationalSpec:
    return OperationalSpec(
        goal="genes expressed higher in bradyzoites",
        criteria=[
            Criterion(
                id="c_expr",
                text="expressed higher in bradyzoites than tachyzoites",
                search_name=_SEARCH,
                role="filter",
                resolved_params={
                    _REF: BoundValue(
                        value=MultiPickValue(values=[reference]), source="chosen"
                    )
                },
                param_display_names={_REF: "Reference Samples"},
                result_count=592,
            )
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c_expr")),
    )


def _deps(answered: OperationalSpec, pending: OperationalSpec) -> LeadDeps:
    graph = StrategyGraph(graph_id="g1", name="strategy", site_id="toxodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id="c_expr", search_name=_SEARCH))
    graph.recompute_roots()
    session = StrategySession(site_id="toxodb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={"c_expr": 592})
    domain = StrategyDomainState(operational_spec=pending)
    domain.answered_spec = answered
    state = pipeline_state("toxodb", user_message_id=uuid4(), domain=domain)
    return lead_deps(state, strategy_session=session)


def _reference_rows(deps: LeadDeps) -> list[tuple[str, int | None]]:
    facts = turn_facts(deps)
    return [
        (row.value, step.count)
        for step in facts.steps
        for row in step.parameters
        if row.name == _REF
    ]


def test_a_built_step_shows_the_value_the_strategy_answers_to() -> None:
    deps = _deps(answered=_spec("ME49 tachyzoite"), pending=_spec("GT1 tachyzoite"))

    assert _reference_rows(deps) == [("ME49 tachyzoite", 592)]
    assert turn_facts(deps).draft is False


def test_a_pushed_edit_shows_its_own_value() -> None:
    deps = _deps(answered=_spec("GT1 tachyzoite"), pending=_spec("GT1 tachyzoite"))

    assert _reference_rows(deps) == [("GT1 tachyzoite", 592)]
