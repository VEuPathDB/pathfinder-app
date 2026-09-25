"""An edit that copies a live subtree adds the copy as steps of its own and
leaves every step the strategy held where it was."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    subtree_ids,
)

from pathfinder.domain.strategy.edit_plan import UnsupportedEditError
from pathfinder.domain.strategy.operational_spec import OperationalSpec, SpecStructure
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
)
from pathfinder.domain.strategy.orthology import restate_copies
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.domain.strategy.stated_shape import (
    criteria_with_steps,
    stated_shape,
)

from ._builders import applied, graph_of, plan
from ._orthology import (
    kept_by_intersect,
    round_trip_spec,
    seed_criteria,
    seed_node,
    trip,
)

_LIVE = ("step_signal", "step_tm", "step_seed")


def _live_seed() -> StrategyStepNode:
    signal, tm = seed_criteria("step_signal", "step_tm")
    return StrategyStepNode(
        id="step_seed",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id=signal.id,
            search_name=signal.search_name,
            parameters=signal.step_parameters,
        ),
        secondary_input=StrategyStepNode(
            id=tm.id, search_name=tm.search_name, parameters=tm.step_parameters
        ),
    )


def _before() -> OperationalSpec:
    return OperationalSpec(
        goal="secreted membrane proteins",
        criteria=seed_criteria("step_signal", "step_tm"),
        structure=SpecStructure(root=seed_node("step_signal", "step_tm")),
    )


def _after() -> OperationalSpec:
    return restate_copies(
        round_trip_spec(
            kept_by_intersect(seed_node("step_signal", "step_tm")),
            seed=seed_criteria("step_signal", "step_tm"),
        )
    )


def test_the_copy_of_a_live_subtree_is_added_as_three_new_steps() -> None:
    ops = plan(_before(), _after(), graph_of(_live_seed()))

    leaves = [op for op in ops if isinstance(op, AddLeafOp)]
    combines = [op for op in ops if isinstance(op, AddCombineOp)]
    transforms = [op for op in ops if isinstance(op, AddTransformOp)]
    assert len(leaves) == 2
    assert len(combines) == 2
    assert [op.step.id for op in transforms] == ["c_to", "c_back"]
    assert {op.step.search_name for op in leaves} == {
        "GenesWithSignalPeptide",
        "GenesByTransmembraneDomains",
    }
    assert {op.step.id for op in leaves}.isdisjoint(_LIVE)


def test_every_step_the_strategy_held_keeps_its_id_and_its_place() -> None:
    root = _live_seed()
    ops = plan(_before(), _after(), graph_of(root))

    graph = applied(root, ops)

    root_id = graph.primary_root_id()
    assert root_id is not None
    top = graph.steps[root_id]
    assert top.operator is CombineOp.INTERSECT
    assert top.primary_input_id == "step_seed"
    assert set(subtree_ids("step_seed", graph.steps)) == set(_LIVE)
    assert len(graph.steps) == len(_LIVE) + 6


def test_the_applied_graph_holds_exactly_the_stated_criteria() -> None:
    root = _live_seed()
    after = _after()
    graph = applied(root, plan(_before(), after, graph_of(root)))
    root_id = graph.primary_root_id()
    assert root_id is not None

    shape = stated_shape(
        graph=graph,
        root_id=root_id,
        criteria=criteria_with_steps([c.id for c in after.criteria], graph.steps),
        outside=set(),
    )

    assert (
        shape.roots_elsewhere,
        shape.adopted,
        shape.lost,
        shape.unstated,
        shape.stranded,
    ) == (False, (), (), (), ())


def test_hydrating_the_result_states_one_criterion_per_step() -> None:
    root = _live_seed()
    graph = applied(root, plan(_before(), _after(), graph_of(root)))

    ast = graph.to_strategy_ast()
    assert ast is not None

    hydrated = spec_from_ast(ast, goal="keep the syntenic orthologs")

    searches = [c.search_name for c in hydrated.criteria]
    assert sorted(searches) == sorted(
        [
            "GenesWithSignalPeptide",
            "GenesByTransmembraneDomains",
            "GenesWithSignalPeptide",
            "GenesByTransmembraneDomains",
            "GenesByOrthologs",
            "GenesByOrthologs",
        ]
    )
    assert len({c.id for c in hydrated.criteria}) == 6


def test_an_edit_that_adds_an_unkept_round_trip_is_refused() -> None:
    root = _live_seed()
    after = round_trip_spec(
        trip(seed_node("step_signal", "step_tm")),
        seed=seed_criteria("step_signal", "step_tm"),
    )

    with pytest.raises(UnsupportedEditError) as exc:
        plan(_before(), after, graph_of(root))

    assert "c_back (Transform by Orthology)" in str(exc.value)


def test_a_copy_that_reaches_the_edit_unrestated_is_refused() -> None:
    root = _live_seed()
    after = round_trip_spec(
        kept_by_intersect(seed_node("step_signal", "step_tm")),
        seed=seed_criteria("step_signal", "step_tm"),
    )

    with pytest.raises(UnsupportedEditError) as exc:
        plan(_before(), after, graph_of(root))

    assert "copy" in str(exc.value)
