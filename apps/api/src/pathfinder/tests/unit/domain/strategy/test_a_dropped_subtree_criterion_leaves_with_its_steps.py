"""A criterion that addresses a whole subtree is dropped with the steps under it.

An inserted saved strategy answers to one criterion, named by the root of the
subtree it expanded into, so the steps inside it carry no criterion of their own.
"""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)

from ._builders import (
    applied,
    graph_of,
    plan,
    shape,
    spec_joined,
    spec_leaf,
    three_step_root,
)

_SAVED = "step_c1"


def _spec_over_a_saved_subtree() -> OperationalSpec:
    """``step_c1`` stands for the two steps it joins; ``step_expr`` is its own."""
    return OperationalSpec(
        goal="find proteases",
        record_type="transcript",
        criteria=[
            Criterion(id=_SAVED, text="my saved protease strategy", role="seed"),
            Criterion(
                id="step_expr",
                text="top decile",
                search_name="GenesByRNASeqEvidence",
                resolved_params={"min_expression_percentile": NumberValue(value=90)},
            ),
        ],
        structure=SpecStructure(
            root=spec_joined(
                CombineOp.INTERSECT, spec_leaf(_SAVED), spec_leaf("step_expr")
            )
        ),
    )


def test_dropping_the_saved_strategy_removes_the_steps_it_expanded_into() -> None:
    root = three_step_root()
    before = _spec_over_a_saved_subtree()
    after = before.model_copy(deep=True)
    after.criteria = [c for c in after.criteria if c.id != _SAVED]
    after.structure = SpecStructure(root=spec_leaf("step_expr"))

    ops = plan(before, after, graph_of(root))

    assert [op.kind for op in ops] == ["deleteStep"]
    assert shape(applied(root, ops)) == "step_expr"
