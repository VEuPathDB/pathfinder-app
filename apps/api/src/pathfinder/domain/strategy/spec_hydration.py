"""Reconstruct an OperationalSpec from a strategy that already exists.

The graph editor, a saved-strategy import and every thread whose checkpoint was
flushed own a strategy no spec describes. The persisted AST holds the searches
and the bound parameter values, so the spec is derived rather than re-asked.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.ast_diff import nodes_of
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps

__all__ = [
    "hidden_params_dropped",
    "sheet_bound",
    "spec_from_ast",
    "spec_stating_the_live_tree",
]


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


def spec_stating_the_live_tree(
    spec: OperationalSpec,
    ast: StrategyAst,
    *,
    sheet_params: Mapping[str, Collection[str]],
    shape_moved: bool = False,
    may_leave_out: Collection[str] = (),
) -> OperationalSpec:
    """The spec restated over the strategy the graph holds now.

    Every live step is a criterion, because an edit is planned against the
    structure and a step it leaves out is one the next edit removes without
    being asked to. ``may_leave_out`` names the steps this spec is entitled to
    leave out, which is how a plan carries a drop it has not pushed. The built
    part of the structure is the strategy's own whenever the spec leaves a step
    out or the tree's shape moved. A criterion the plan states and no step
    answers is re-joined at the plan's root combine when that is where the plan
    put it; any other plan is left alone.
    """
    derived = spec_from_ast(ast, goal=spec.goal)
    if derived.structure is None:
        return spec
    nodes = nodes_of(ast)
    stated = {criterion.id for criterion in spec.criteria}
    if any(
        node.infer_kind() == "combine" for cid in stated if (node := nodes.get(cid))
    ):
        # One criterion stands for the whole subtree under a combine, which is
        # how an expanded saved strategy answers for the criterion that names
        # it, so the tree does not say how many criteria the spec has.
        return spec
    left_out = {c.id for c in derived.criteria if c.id in may_leave_out} - stated
    missing = [c for c in derived.criteria if c.id not in stated | left_out]
    if not missing and not shape_moved:
        return spec
    pending = structure_criteria(spec.structure) - set(nodes)
    root = derived.structure.root
    if pending:
        joined = _pending_joined_at_the_root(spec.structure, pending, root)
        if joined is None:
            return spec
        root = joined
    restated = spec.model_copy(deep=True)
    restated.criteria = [
        *restated.criteria,
        *(_sheet_stated(criterion, sheet_params) for criterion in missing),
    ]
    restated.structure = SpecStructure(root=root)
    return spec_without_steps(restated, left_out)


def _pending_joined_at_the_root(
    structure: SpecStructure | None,
    pending: frozenset[str],
    built_root: StructureNode,
) -> StructureNode | None:
    """The live tree joined to the criteria the plan hangs off its root combine.

    Nothing when the plan puts one of them anywhere else, which is a plan the
    strategy has not reached and the edit refuses with a way forward.
    """
    if structure is None or structure.root.kind != "combine":
        return None
    hanging = [
        node
        for node in structure.root.inputs
        if node.kind == "leaf" and node.criterion_id in pending
    ]
    if {node.criterion_id for node in hanging} != set(pending):
        return None
    return StructureNode(
        kind="combine",
        operator=structure.root.operator,
        inputs=[built_root, *hanging],
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


def hidden_params_dropped(
    spec: OperationalSpec, *, sheet_params: Mapping[str, Collection[str]]
) -> OperationalSpec:
    """A copy of the spec where each criterion states only the sheet's parameters.

    A hidden or computed parameter is WDK's, and a criterion that states one
    offers the model a value the parameter sheet then refuses. A search the
    mapping does not name keeps its values, because nothing says which of
    them the sheet shows.
    """
    criteria = [_sheet_stated(criterion, sheet_params) for criterion in spec.criteria]
    return spec.model_copy(update={"criteria": criteria})


def _sheet_stated(
    criterion: Criterion, sheet_params: Mapping[str, Collection[str]]
) -> Criterion:
    """The criterion stating only the parameters its search's sheet shows."""
    if criterion.search_name not in sheet_params:
        return criterion
    return criterion.model_copy(
        update={
            "resolved_params": sheet_bound(
                criterion.resolved_params, sheet_params[criterion.search_name]
            )
        }
    )


def sheet_bound(
    params: Mapping[str, ParamValue], sheet: Collection[str] | None
) -> dict[str, ParamValue]:
    """The values a search's sheet shows. An unread sheet keeps them all."""
    if sheet is None:
        return dict(params)
    return {name: value for name, value in params.items() if name in sheet}
