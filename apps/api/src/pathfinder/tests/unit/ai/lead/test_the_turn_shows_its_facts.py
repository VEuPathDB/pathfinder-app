"""The facts part a turn shows: its steps in tree order with their values and
who set them, the root count, and what the turn saved, tested and retired."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    WithdrawnLifecycle,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.strategy.requirement_lifecycle import RetiredRequirement
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_rationale import SearchRationale, said_beside
from pathfinder.domain.turn_facts import ParameterFact, RetiredFact, SavedSetFact
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_PERCENTILE = "min_expression_percentile"


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="trophozoite peptidases",
        criteria=[
            Criterion(
                id="s_go",
                text="peptidase activity",
                search_name="GenesByGoTerm",
                search_display_name="GO Term",
                resolved_params=bound({"GoTerm": StringValue(value="GO:0008234")}),
                param_display_names={"GoTerm": "GO term"},
            ),
            Criterion(
                id="s_rna",
                text="expressed in trophozoites",
                search_name="GenesByRNASeqPercentile",
                search_display_name="Trophozoite RNA-Seq percentile",
                resolved_params=bound(
                    {_PERCENTILE: NumberValue(value=80)}, defaulted=[_PERCENTILE]
                ),
                param_display_names={_PERCENTILE: "Minimum expression percentile"},
                measurements=[
                    Measurement(
                        kind="loosest_bound", param=_PERCENTILE, count=8201, reading="0"
                    )
                ],
                result_count=1665,
            ),
        ],
    )


def _session() -> StrategySession:
    graph = StrategyGraph(graph_id="g1", name="Peptidases", site_id="amoebadb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="s_and",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(id="s_go", search_name="GenesByGoTerm"),
            secondary_input=StrategyStepNode(
                id="s_rna", search_name="GenesByRNASeqPercentile"
            ),
        )
    )
    graph.recompute_roots()
    session = StrategySession(site_id="amoebadb")
    session.graph = graph
    session.sync_state = WDKSyncState(
        step_counts={"s_go": 220, "s_rna": 1665, "s_and": 74}
    )
    return session


def _deps(*, built: bool = True) -> LeadDeps:
    state = pipeline_state(
        "amoebadb",
        user_prompt="Peptidases expressed in trophozoites.",
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=_spec()),
    )
    return lead_deps(state, strategy_session=_session() if built else None)


def test_the_steps_are_shown_in_tree_order_with_their_counts() -> None:
    facts = turn_facts(_deps())

    assert [(s.display_name, s.operator, s.count) for s in facts.steps] == [
        ("GO Term", None, 220),
        ("Trophozoite RNA-Seq percentile", None, 1665),
        ("Combine", "INTERSECT", 74),
    ]
    assert (facts.root_count, facts.record_noun, facts.draft) == (74, "gene", False)


def test_a_default_value_is_shown_with_its_measurement() -> None:
    rna = turn_facts(_deps()).steps[1]

    assert rna.parameters == [
        ParameterFact(
            name=_PERCENTILE,
            display_name="Minimum expression percentile",
            value="80",
            source="default",
            notes=[
                (
                    "Minimum expression percentile at the site's default of 80: "
                    "1,665 genes; at 0: 8,201"
                )
            ],
        )
    ]


def test_a_stated_value_is_shown_with_nothing_beside_it() -> None:
    go = turn_facts(_deps()).steps[0]

    assert [(p.display_name, p.value, p.source, p.notes) for p in go.parameters] == [
        ("GO term", "GO:0008234", "stated", [])
    ]


def test_a_draft_shows_its_bound_criteria_with_the_counts_they_bound_at() -> None:
    facts = turn_facts(_deps(built=False))

    assert [(s.display_name, s.count) for s in facts.steps] == [
        ("GO Term", None),
        ("Trophozoite RNA-Seq percentile", 1665),
    ]
    assert (facts.draft, facts.root_count, facts.strategy_url) == (True, None, None)


def test_a_withdrawn_requirement_is_shown_retired_and_never_as_a_gap() -> None:
    deps = _deps()
    deps.state.domain.retired_requirements = [
        RetiredRequirement(
            constraint=Constraint(
                kind=ConstraintKind.OTHER,
                label="expression cutoff",
                requested_value="above the 50th percentile",
                source=ConstraintSource.USER_EXPLICIT,
            ),
            lifecycle=WithdrawnLifecycle(turn_id="t4"),
        )
    ]
    facts = turn_facts(deps)

    assert facts.retired == [
        RetiredFact(requirement="above the 50th percentile", state="withdrawn")
    ]
    assert facts.gaps == []


def test_the_sets_saved_and_the_controls_tested_this_turn_are_shown() -> None:
    deps = _deps()
    markers = deps.state.turn_markers
    markers.record_gene_set(
        CreatedGeneSet(id="gs-1", name="vaccine candidates draft", gene_count=39)
    )
    markers.record_control_tests(
        [
            ControlTestRun(
                tool_call_id="call_1",
                evidence=ControlTestEvidence(
                    tested_label="Peptidases",
                    positive=ControlSetEvidence(
                        returned=["EHI_001730", "EHI_004440"],
                        not_returned=["EHI_009910"],
                    ),
                ),
            )
        ]
    )
    facts = turn_facts(deps)

    assert facts.saved == [
        SavedSetFact(kind="gene_set", name="vaccine candidates draft", count=39)
    ]
    assert [r.sentence for r in facts.control_results] == [
        "Peptidases: 2 of 3 positive controls returned"
    ]


def test_a_refusal_is_shown_whole() -> None:
    refusal = "status_code: 400, " + "the provider refused the request " * 10

    assert turn_facts(_deps(), refusal=refusal).refusal == refusal


def test_a_step_shows_why_it_runs_its_search_beside_its_name() -> None:
    deps = _deps()
    spec = deps.state.domain.operational_spec
    assert spec is not None
    spec.criteria[0] = spec.criteria[0].model_copy(
        update={
            "rationale": SearchRationale(
                search_name="GenesByGoTerm",
                basis="only_match",
                term="peptidase activity",
                reason="no other search names the activity",
                tool_call_id="call_bind",
            )
        }
    )
    facts = turn_facts(deps)

    assert facts.steps[0].reason == (
        "peptidase activity: no other search names the activity"
    )
    assert said_beside(facts.text(), "GO Term", "peptidase activity")
