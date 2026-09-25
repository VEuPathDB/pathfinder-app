"""A criterion waiting for its analysis is routed to the EDA tools, by its id."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead._delete_rules import steps_outside_the_strategy
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_pins import (
    eda_route_blocks,
    pinned_detached_steps,
    pinned_turn_briefing,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    user_intent,
)

_DATASET = "DS_70dd50fed7"
_CRITERION = "essential in blood stages"


def _waiting(criterion_id: str = "c_essential", text: str = _CRITERION) -> Criterion:
    return Criterion(id=criterion_id, text=text, needs_analysis_on=_DATASET)


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _spec(*, waiting: bool = True, kinases: bool = True) -> OperationalSpec:
    kinase = Criterion(id="step_k1", text="PF00069 kinases", search_name="GenesByText")
    criteria = [*([kinase] if kinases else []), *([_waiting()] if waiting else [])]
    leaves = [_leaf(c.id) for c in criteria]
    return OperationalSpec(
        goal="essential kinases",
        criteria=criteria,
        structure=SpecStructure(
            root=(
                StructureNode(
                    kind="combine", operator=CombineOp.INTERSECT, inputs=leaves
                )
                if len(leaves) > 1
                else leaves[0]
            )
        ),
    )


def _eda_leaf(step_id: str, dataset_id: str = _DATASET) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByEdaSubset",
        parameters={"eda_dataset_id": StringValue(value=dataset_id)},
    )


def _session(*nodes: StrategyStepNode, combined: bool = False) -> StrategySession:
    """A session holding the given steps, optionally under one combine."""
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    if combined:
        root = StrategyStepNode(
            id="step_c1",
            search_name="__combine__",
            operator=CombineOp.INTERSECT,
            primary_input=nodes[0],
            secondary_input=nodes[1],
        )
        graph.steps = flatten_tree(root)
    else:
        for node in nodes:
            graph.steps.update(flatten_tree(node))
    graph.recompute_roots()
    session.graph = graph
    return session


def _deps(
    session: StrategySession,
    *,
    spec: OperationalSpec | None,
    classification: IntentClassification = IntentClassification.EDIT_STRATEGY,
) -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            user_prompt="add the essentiality comparison",
            user_message_id=uuid4(),
            domain=StrategyDomainState(operational_spec=spec),
        ),
        intent=user_intent(classification),
        strategy_session=session,
    )
    deps.state.turn_markers.intent_classified = True
    return deps


class TestTheRouteThePinPrints:
    def _pin(self, deps: LeadDeps) -> str:
        pinned = pinned_turn_briefing(run_context_for(deps))
        assert pinned is not None
        return pinned

    def test_the_block_names_the_criterion_its_dataset_and_its_id(self) -> None:
        pinned = self._pin(
            _deps(
                _session(StrategyStepNode(id="step_k1", search_name="GenesByText")),
                spec=_spec(),
            ),
        )

        assert f"## Build the EDA criterion: {_CRITERION}" in pinned
        assert f'open_eda_analysis(dataset_id="{_DATASET}"' in pinned
        assert "set_eda_filters" in pinned
        assert "preview_eda_subset" in pinned
        assert 'create_eda_step(criterion_id="c_essential")' in pinned
        assert "Never ask the user for an analysis specification" in pinned

    def test_two_waiting_criteria_on_one_dataset_are_each_routed(self) -> None:
        """One dataset holds as many comparisons as the request states."""
        spec = _spec(kinases=False)
        spec.criteria.append(_waiting("c_24h_vs_36_up", "higher at 24 h than 36 h"))
        spec.structure = SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[_leaf("c_essential"), _leaf("c_24h_vs_36_up")],
            )
        )

        blocks = eda_route_blocks(run_context_for(_deps(_session(), spec=spec)))

        assert len(blocks) == 2
        assert 'create_eda_step(criterion_id="c_essential")' in blocks[0]
        assert 'create_eda_step(criterion_id="c_24h_vs_36_up")' in blocks[1]

    def test_a_criterion_with_no_step_is_built_before_the_export(self) -> None:
        """The export joins a strategy, so the strategy is built first."""
        pinned = self._pin(_deps(_session(), spec=_spec()))

        assert (
            "0. build_strategy for the remaining criteria (['step_k1']) so the "
            "export has a strategy to join"
        ) in pinned

    def test_a_spec_whose_criteria_all_have_steps_asks_for_no_build(self) -> None:
        session = _session(StrategyStepNode(id="step_k1", search_name="GenesByText"))

        pinned = self._pin(_deps(session, spec=_spec()))

        assert "build_strategy" not in pinned

    def test_a_turn_that_does_not_build_pins_no_route(self) -> None:
        """The route names tools this turn's classification withholds."""
        deps = _deps(
            _session(_eda_leaf("step_af9d7803")),
            spec=_spec(),
            classification=IntentClassification.FOLLOW_UP_QUESTION,
        )

        assert eda_route_blocks(run_context_for(deps)) == []
        assert pinned_turn_briefing(run_context_for(deps)) is None

    def test_a_spec_with_no_waiting_criterion_pins_no_route(self) -> None:
        deps = _deps(_session(_eda_leaf("step_af9d7803")), spec=_spec(waiting=False))

        assert eda_route_blocks(run_context_for(deps)) == []
        assert pinned_turn_briefing(run_context_for(deps)) is None


class TestTheStepsOutsideTheStrategy:
    def _cited(self, session: StrategySession, step_id: str) -> StrategySession:
        """Record the push that names this step the WDK strategy's root step."""
        session.sync_state = WDKSyncState(
            wdk_step_ids={step_id: 9001},
            wdk_strategy_id=42,
            wdk_step_tree=WDKStepTree(step_id=9001),
        )
        return session

    def _split_session(self) -> StrategySession:
        session = _session(
            StrategyStepNode(id="step_k1", search_name="GenesByText"),
            StrategyStepNode(id="step_k2", search_name="GenesByText"),
            combined=True,
        )
        graph = session.graph
        assert graph is not None
        graph.steps.update(flatten_tree(_eda_leaf("step_da5a2302")))
        graph.recompute_roots()
        return session

    def test_a_cited_root_makes_the_delete_the_first_way_out(self) -> None:
        session = self._cited(self._split_session(), "step_c1")

        pinned = pinned_detached_steps(run_context_for(_deps(session, spec=_spec())))

        assert pinned is not None
        assert pinned.startswith("Steps outside the strategy: step_da5a2302")
        assert "delete_step(step_id)" in pinned
        assert "create_eda_step(replace_step_id=...)" in pinned

    def _with_a_loose_component(self, session: StrategySession) -> StrategySession:
        graph = session.graph
        assert graph is not None
        graph.steps.update(
            flatten_tree(
                StrategyStepNode(
                    id="step_c9",
                    search_name=COMBINE_SEARCH_NAME,
                    operator=CombineOp.INTERSECT,
                    primary_input=StrategyStepNode(
                        id="step_k8", search_name="GenesByText"
                    ),
                    secondary_input=StrategyStepNode(
                        id="step_k9", search_name="GenesByText"
                    ),
                ),
            ),
        )
        graph.recompute_roots()
        return session

    def test_a_thread_no_push_named_a_root_for_calls_nothing_loose(self) -> None:
        """No root is the strategy there, so no root is outside it either."""
        pinned = pinned_detached_steps(
            run_context_for(_deps(self._split_session(), spec=_spec())),
        )

        assert pinned is not None
        assert pinned.startswith("This conversation holds 2 roots and no push says")
        assert "step_c1 (3 steps)" in pinned
        assert "step_da5a2302 (1 step)" in pinned
        assert "Steps outside the strategy" not in pinned

    def test_a_root_of_one_step_is_named_as_the_one_a_delete_takes(self) -> None:
        """One multi-step root does not suppress the offer for a one-step root."""
        pinned = pinned_detached_steps(
            run_context_for(
                _deps(
                    self._with_a_loose_component(self._split_session()), spec=_spec()
                ),
            ),
        )

        assert pinned is not None
        assert "takes a root of one step: step_da5a2302" in pinned
        assert "A root of more than one step is refused" in pinned
        assert "clear_strategy" in pinned

    def test_the_strategy_is_never_named_as_a_step_outside_itself(self) -> None:
        """The cited root is the strategy, whatever component is larger."""
        session = _session(StrategyStepNode(id="step_main", search_name="GenesByText"))
        self._cited(session, "step_main")
        self._with_a_loose_component(session)

        pinned = pinned_detached_steps(run_context_for(_deps(session, spec=_spec())))

        graph = session.graph
        assert graph is not None
        assert steps_outside_the_strategy(graph, session.sync_state) == [
            "step_c9",
            "step_k8",
            "step_k9",
        ]
        assert pinned is not None
        assert "step_main" not in pinned
        assert pinned.startswith("Steps outside the strategy: step_c9")

    def test_a_turn_that_does_not_build_pins_nothing(self) -> None:
        """Both ways out are tools this turn's classification withholds."""
        session = _session(
            StrategyStepNode(id="step_k1", search_name="GenesByText"),
            StrategyStepNode(id="step_k2", search_name="GenesByText"),
            combined=True,
        )
        graph = session.graph
        assert graph is not None
        graph.steps.update(flatten_tree(_eda_leaf("step_da5a2302")))
        graph.recompute_roots()
        deps = _deps(
            session,
            spec=_spec(),
            classification=IntentClassification.FOLLOW_UP_QUESTION,
        )

        assert sorted(graph.roots) == ["step_c1", "step_da5a2302"]
        assert pinned_detached_steps(run_context_for(deps)) is None

    def test_a_strategy_of_one_tree_pins_nothing(self) -> None:
        session = _session(
            StrategyStepNode(id="step_k1", search_name="GenesByText"),
            StrategyStepNode(id="step_k2", search_name="GenesByText"),
            combined=True,
        )

        graph = session.graph
        assert graph is not None
        assert sorted(graph.roots) == ["step_c1"]
        assert (
            pinned_detached_steps(run_context_for(_deps(session, spec=_spec()))) is None
        )
