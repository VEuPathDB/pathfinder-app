"""A criterion the baseline states with no step is one the edit introduces.

The strategy answers whether a criterion holds a step, so a criterion an
earlier dispatch framed and never built is added rather than refused.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.strategy.edit_plan import UnsupportedEditError
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    UpdateStepParamsOp,
)

from ._builders import (
    graph_of,
    plan,
    spec_joined,
    spec_leaf,
    spec_of,
    three_step_root,
)

_UNBUILT = "c_tm"
_SEARCH = "GenesByTransmembraneDomains"
_PARAM = "min_tm"


def _unbuilt(value: float | None = None) -> Criterion:
    """The criterion the earlier dispatch framed, open or answered."""
    return Criterion(
        id=_UNBUILT,
        text="two or more transmembrane domains",
        search_name=_SEARCH,
        resolved_params={} if value is None else {_PARAM: NumberValue(value=value)},
        open_params=[]
        if value is not None
        else [OpenSlot(criterion_id=_UNBUILT, param_name=_PARAM)],
    )


def _baseline(root: StrategyStepNode) -> OperationalSpec:
    """The committed spec: three criteria on steps, one with no step."""
    before = spec_of(root)
    assert before.structure is not None
    before.criteria.append(_unbuilt())
    before.structure = SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT, before.structure.root, spec_leaf(_UNBUILT)
        )
    )
    return before


def _answered(before: OperationalSpec) -> OperationalSpec:
    after = before.model_copy(deep=True)
    after.criteria = [c for c in after.criteria if c.id != _UNBUILT]
    after.criteria.append(_unbuilt(2))
    return after


def test_the_unbuilt_criterion_is_added_with_the_combine_the_structure_states() -> None:
    root = three_step_root()
    before = _baseline(root)

    ops = plan(before, _answered(before), graph_of(root))

    assert [op.kind for op in ops] == ["addLeaf", "addCombine"]
    add_leaf, add_combine = ops
    assert isinstance(add_leaf, AddLeafOp)
    assert add_leaf.step.id == _UNBUILT
    assert add_leaf.step.search_name == _SEARCH
    assert add_leaf.step.parameters == {_PARAM: NumberValue(value=2)}
    assert isinstance(add_combine, AddCombineOp)
    assert add_combine.left_id == "step_c2"
    assert add_combine.right_id == _UNBUILT
    assert add_combine.step.operator is CombineOp.INTERSECT


def test_an_unbuilt_criterion_the_edit_restates_is_still_added() -> None:
    """The diff calls it kept, and the strategy still holds no step for it."""
    root = three_step_root()
    before = _baseline(root)

    ops = plan(before, before.model_copy(deep=True), graph_of(root))

    assert [op.kind for op in ops] == ["addLeaf", "addCombine"]


def test_a_built_criterion_beside_it_is_changed_on_its_live_step() -> None:
    root = three_step_root()
    before = _baseline(root)
    after = _answered(before)
    for criterion in after.criteria:
        if criterion.id == "step_expr":
            criterion.resolved_params = {
                "min_expression_percentile": NumberValue(value=75)
            }

    ops = plan(before, after, graph_of(root))

    updates = [op for op in ops if isinstance(op, UpdateStepParamsOp)]
    assert [op.step_id for op in updates] == ["step_expr"]
    assert [op.step.id for op in ops if isinstance(op, AddLeafOp)] == [_UNBUILT]


def test_a_criterion_outside_the_structure_mints_nothing() -> None:
    """An option binds a value on another criterion's search, not a step."""
    root = three_step_root()
    before = spec_of(root)
    before.criteria.append(
        Criterion(
            id="c_dataset",
            text="read the sexual stage dataset",
            search_name="GenesByRNASeqEvidence",
        )
    )

    assert plan(before, before.model_copy(deep=True), graph_of(root)) == []


def test_a_spec_that_states_none_of_the_live_steps_is_refused() -> None:
    """An edit removes a step the spec it answers to never mentions."""
    root = three_step_root()
    labelled = OperationalSpec(
        goal="find proteases",
        record_type="transcript",
        criteria=[
            Criterion(id="c1_text", text="protease text", search_name="GenesByText")
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c1_text")
        ),
    )

    with pytest.raises(UnsupportedEditError) as excinfo:
        plan(labelled, labelled.model_copy(deep=True), graph_of(root))

    assert "step_text" in str(excinfo.value)
