from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.refusal import Check, Problems, RefusalKey
from strategist.domain.strategy.operational_spec import (
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.operations import (
    UpdateCombineOperatorOp,
    UpdateStepParamsOp,
)
from strategist.domain.strategy.operations.apply import PlanDeparturesError
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.domain.strategy.spec_edit_guard import StatedCriterion
from strategist.services.strategies import spec_build, stated_sides
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.spec_build import build_strategy_from_spec
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
)

_TWO_TYPES = Problems.one(
    RefusalKey(check=Check.THE_TREE_TO_ITS_RECORD_CLASSES),
    "the tree joins two record types",
)
_STATED = {
    "c_fold": ("min_fold", "4.0", "4"),
    "c_direction": ("direction", "up", "up-regulated"),
    "c_organism": ("organism", "Pf3D7", "PvP01"),
    "c_stage": ("stage", "gametocyte", "ring"),
}


def _leaf(criterion: str, value: str) -> StrategyStepNode:
    name = _STATED[criterion][0]
    return StrategyStepNode(
        id=criterion,
        search_name="GenesByTextSearch",
        display_name=criterion,
        parameters={name: StringValue(value=value)},
    )


def _tree(pick: int) -> StrategyStepNode:
    leaves = [
        _leaf(c, written[pick])
        for c, written in ((c, v[1:]) for c, v in _STATED.items())
    ]
    return StrategyStepNode(
        id="j_all",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(
            id="j_left",
            search_name="__combine__",
            operator=CombineOp.UNION,
            primary_input=leaves[0],
            secondary_input=leaves[1],
        ),
        secondary_input=StrategyStepNode(
            id="j_right",
            search_name="__combine__",
            operator=CombineOp.UNION,
            primary_input=leaves[2],
            secondary_input=leaves[3],
        ),
    )


def _stated() -> dict[str, StatedCriterion]:
    return {
        criterion: StatedCriterion(
            text=f"the {criterion} words", values={name: StringValue(value=stated)}
        )
        for criterion, (name, stated, _written) in _STATED.items()
    }


def _thread(**fields: Any) -> StrategyMutationContext:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Gametocytes", site_id="plasmodb")
    graph.record_type = "transcript"
    session.graph = graph
    return StrategyMutationContext(
        site_id="plasmodb", strategy_session=session, conversation_id=None, **fields
    )


async def _as_written(*_args: object, **kwargs: Any) -> ValidatedParams:
    params: dict[str, ParamValue] = {**kwargs.get("context", {}), **kwargs["stated"]}
    return ValidatedParams(params=params, record_class="transcript")


async def test_a_build_departing_in_four_values_names_all_four(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    monkeypatch.setattr(stated_sides, "validate_parameters", _as_written)

    with pytest.raises(PlanDeparturesError) as refused:
        await build_strategy_from_spec(
            deps=_thread(stated_values=_stated()), root=_tree(1)
        )

    problems = refused.value.problems
    assert [
        (p.key.check, p.key.criterion, p.key.parameter) for p in problems.found
    ] == [
        (Check.THE_VALUE_TO_THE_SPEC, criterion, name)
        for criterion, (name, _stated, _written) in _STATED.items()
    ]
    assert str(refused.value) == problems.text()
    assert env.wdk.writes == []


async def test_a_batch_that_joins_against_the_spec_and_moves_a_value_names_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)
    monkeypatch.setattr(stated_sides, "validate_parameters", _as_written)
    structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode(kind="leaf", criterion_id="c_fold"),
                StructureNode(kind="leaf", criterion_id="c_direction"),
            ],
        )
    )
    deps = _thread(
        stated_values=_stated(),
        stated_criteria=frozenset({"c_fold", "c_direction"}),
        stated_structure=structure,
    )
    graph = deps.strategy_session.graph
    assert graph is not None
    held = _tree(0).primary_input
    assert held is not None
    graph.steps = flatten_tree(held)
    graph.recompute_roots()
    deps.strategy_session.sync_state = WDKSyncState()

    with pytest.raises(PlanDeparturesError) as refused:
        await apply_operations_and_commit(
            deps=deps,
            ops=[
                UpdateCombineOperatorOp(step_id="j_left", operator=CombineOp.INTERSECT),
                UpdateStepParamsOp(
                    step_id="c_fold", parameters={"min_fold": StringValue(value="4")}
                ),
            ],
        )

    assert [p.key for p in refused.value.problems.found] == [
        RefusalKey(check=Check.THE_JOIN_TO_THE_SPEC, criterion="c_direction + c_fold"),
        RefusalKey(
            check=Check.THE_VALUE_TO_THE_SPEC,
            criterion="c_fold",
            search="GenesByTextSearch",
            parameter="min_fold",
        ),
    ]


async def test_a_build_with_a_record_class_problem_and_a_value_problem_names_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)
    monkeypatch.setattr(stated_sides, "validate_parameters", _as_written)

    async def _two_types(*_args: object) -> Problems:
        return _TWO_TYPES

    monkeypatch.setattr(spec_build, "what_the_site_cannot_run", _two_types)

    with pytest.raises(PlanDeparturesError) as refused:
        await build_strategy_from_spec(
            deps=_thread(stated_values=_stated()), root=_tree(1)
        )

    found = refused.value.problems.found
    assert (found[0], [p.key.check for p in found[1:]]) == (
        _TWO_TYPES.found[0],
        [Check.THE_VALUE_TO_THE_SPEC] * 4,
    )
