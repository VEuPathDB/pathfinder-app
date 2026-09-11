"""Reconstruct an OperationalSpec from a strategy that already exists.

The graph editor, a saved-strategy import and every thread whose checkpoint was
flushed own a strategy no spec describes. The persisted AST holds the searches
and the bound parameter values, so the spec is derived rather than re-asked.
"""

from __future__ import annotations

from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)

__all__ = ["spec_from_ast"]


def spec_from_ast(ast: StrategyAst, *, goal: str) -> OperationalSpec:
    """Reconstruct the spec a strategy would have had.

    One criterion per non-combine node, keyed on the node's step id, holding
    the parameters the node carries. The structure mirrors the tree. The
    criterion text is the step's label, so no code may derive a value from it.
    """
    seed_id = _deepest_primary_leaf(ast.root).id
    criteria: list[Criterion] = []
    structure = _structure_of(ast.root, seed_id, criteria)
    return OperationalSpec(
        goal=goal,
        title=ast.name or "",
        record_type=ast.record_type,
        criteria=criteria,
        structure=SpecStructure(root=structure),
    )


def _deepest_primary_leaf(node: StrategyStepNode) -> StrategyStepNode:
    """The step at the bottom of the primary-input chain."""
    while node.primary_input is not None:
        node = node.primary_input
    return node


def _structure_of(
    node: StrategyStepNode,
    seed_id: str,
    criteria: list[Criterion],
) -> StructureNode:
    kind = node.infer_kind()
    inputs = [_structure_of(child, seed_id, criteria) for child in node.inputs()]
    if kind == "combine":
        return StructureNode(kind="combine", operator=node.operator, inputs=inputs)
    criteria.append(
        Criterion(
            id=node.id,
            text=node.display_name or f"{node.search_name} step",
            search_name=node.search_name,
            role=_role_of(node.id, kind, seed_id),
            resolved_params=dict(node.parameters),
        )
    )
    if kind == "transform":
        return StructureNode(kind="transform", criterion_id=node.id, inputs=inputs)
    return StructureNode(kind="leaf", criterion_id=node.id)


def _role_of(node_id: str, kind: str, seed_id: str) -> CriterionRole:
    if kind == "transform":
        return "transform"
    if node_id == seed_id:
        return "seed"
    return "filter"
