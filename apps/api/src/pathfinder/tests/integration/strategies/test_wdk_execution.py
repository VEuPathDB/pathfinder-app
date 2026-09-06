from __future__ import annotations

import pytest
from veupathdb.domain.parameters.values import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.tree import leaves, walk

from pathfinder.tests.integration.strategies.conftest import BuildAndRead

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_ORGANISM = "Plasmodium falciparum 3D7"


def _text_leaf(step_id: str, expression: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByText",
        parameters={
            "text_expression": StringValue(value=expression),
            "text_fields": MultiPickValue(values=["product"]),
            "document_type": StringValue(value="gene"),
            "text_search_organism": MultiPickValue(values=[_ORGANISM]),
        },
    )


def _combine(
    operator: CombineOp,
    left: StrategyStepNode,
    right: StrategyStepNode,
    step_id: str = "combine",
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="__combine__",
        operator=operator,
        primary_input=left,
        secondary_input=right,
    )


def _text_of(step: StrategyStepNode) -> str:
    value: ParamValue | None = step.parameters.get("text_expression")
    assert isinstance(value, StringValue)
    return value.value


async def test_union_combine_roundtrips_operator_and_leaf_params(
    wdk_builder: BuildAndRead,
) -> None:
    root = _combine(
        CombineOp.UNION,
        _text_leaf("a", "kinase"),
        _text_leaf("b", "phosphatase"),
    )
    rt = await wdk_builder(root)

    assert rt.decoded.root.operator == CombineOp.UNION
    assert {_text_of(leaf) for leaf in leaves(rt.decoded.root)} == {
        "kinase",
        "phosphatase",
    }
    organisms = {
        tuple(v.values)
        for leaf in leaves(rt.decoded.root)
        if isinstance((v := leaf.parameters["text_search_organism"]), MultiPickValue)
    }
    assert organisms == {(_ORGANISM,)}


@pytest.mark.parametrize(
    "operator",
    [CombineOp.UNION, CombineOp.INTERSECT, CombineOp.MINUS, CombineOp.RMINUS],
)
async def test_each_combine_operator_survives_wdk_roundtrip(
    wdk_builder: BuildAndRead, operator: CombineOp
) -> None:
    root = _combine(operator, _text_leaf("a", "kinase"), _text_leaf("b", "protease"))
    rt = await wdk_builder(root)
    assert rt.decoded.root.operator == operator


async def test_three_leaf_nested_topology_survives(
    wdk_builder: BuildAndRead,
) -> None:
    inner = _combine(
        CombineOp.UNION,
        _text_leaf("a", "kinase"),
        _text_leaf("b", "protease"),
        step_id="combine_inner",
    )
    root = _combine(
        CombineOp.INTERSECT,
        inner,
        _text_leaf("c", "transporter"),
        step_id="combine_outer",
    )
    rt = await wdk_builder(root)

    text_leaves = leaves(rt.decoded.root)
    assert len([n for n in walk(rt.decoded.root) if len(n.inputs()) == 2]) == 2
    assert len(text_leaves) == 3
    assert {_text_of(leaf) for leaf in text_leaves} == {
        "kinase",
        "protease",
        "transporter",
    }
    assert rt.decoded.root.operator == CombineOp.INTERSECT
