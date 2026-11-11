from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_tree import build_step_tree
from pathfinder.tests._support.bound_values import bound

_PF = MultiPickValue(values=["Plasmodium falciparum 3D7"])
_IDS = ["ortho", "pknoh", "crispr", "screen", "pkno", "pber"]


def _criterion(cid: str) -> Criterion:
    return Criterion(
        id=cid,
        text=f"genes the {cid} search returns",
        search_name=f"GenesBy{cid.title()}",
        resolved_params=bound({"organism": _PF}),
    )


def _leaf(cid: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=cid)


def _union(*cids: str) -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=CombineOp.UNION,
        inputs=[_leaf(cid) for cid in cids],
    )


def _tree(operator: CombineOp, *inputs: StructureNode) -> StrategyStepNode:
    spec = OperationalSpec(
        goal="genes from the ortholog pattern that some study calls essential",
        criteria=[_criterion(cid) for cid in _IDS],
        structure=SpecStructure(
            root=StructureNode(kind="combine", operator=operator, inputs=list(inputs))
        ),
    )
    return build_step_tree(spec).root


def _searches(node: StrategyStepNode | None) -> list[str]:
    if node is None:
        return []
    if node.primary_input is None:
        return [node.search_name]
    return [*_searches(node.primary_input), *_searches(node.secondary_input)]


def test_a_leaf_intersected_with_a_union_sits_on_the_secondary_side() -> None:
    root = _tree(
        CombineOp.INTERSECT,
        _leaf("ortho"),
        _union("pknoh", "crispr", "screen", "pkno", "pber"),
    )

    assert root.operator is CombineOp.INTERSECT
    assert root.secondary_input is not None
    assert root.secondary_input.search_name == "GenesByOrtho"
    assert root.primary_input is not None
    assert root.primary_input.operator is CombineOp.UNION
    assert _searches(root.primary_input) == [
        "GenesByPknoh",
        "GenesByCrispr",
        "GenesByScreen",
        "GenesByPkno",
        "GenesByPber",
    ]


def test_a_minus_from_a_leaf_mirrors_to_a_right_minus() -> None:
    root = _tree(CombineOp.MINUS, _leaf("ortho"), _union("pknoh", "crispr"))

    assert root.operator is CombineOp.RMINUS
    assert root.secondary_input is not None
    assert root.secondary_input.search_name == "GenesByOrtho"
    assert _searches(root.primary_input) == ["GenesByPknoh", "GenesByCrispr"]


def test_a_combine_of_two_leaves_keeps_its_order() -> None:
    root = _tree(CombineOp.MINUS, _leaf("ortho"), _leaf("pber"))

    assert root.operator is CombineOp.MINUS
    assert _searches(root) == ["GenesByOrtho", "GenesByPber"]


def test_a_combine_of_two_groups_keeps_its_order() -> None:
    root = _tree(CombineOp.MINUS, _union("ortho", "pknoh"), _union("crispr", "screen"))

    assert root.operator is CombineOp.MINUS
    assert _searches(root.primary_input) == ["GenesByOrtho", "GenesByPknoh"]
    assert _searches(root.secondary_input) == ["GenesByCrispr", "GenesByScreen"]


def test_a_leaf_folded_onto_a_group_stays_on_the_secondary_side() -> None:
    root = _tree(
        CombineOp.INTERSECT, _leaf("ortho"), _union("pknoh", "crispr"), _leaf("pber")
    )

    assert root.secondary_input is not None
    assert root.secondary_input.search_name == "GenesByPber"
    inner = root.primary_input
    assert inner is not None
    assert inner.secondary_input is not None
    assert inner.secondary_input.search_name == "GenesByOrtho"
