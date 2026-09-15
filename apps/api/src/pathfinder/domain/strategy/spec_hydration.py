"""Reconstruct an OperationalSpec from a strategy that already exists.

The graph editor, a saved-strategy import and every thread whose checkpoint was
flushed own a strategy no spec describes. The persisted AST holds the searches
and the bound parameter values, so the spec is derived rather than re-asked.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    criteria_under,
    structure_criteria,
)

__all__ = ["hidden_params_dropped", "spec_from_ast", "spec_stating_every_step"]


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


def spec_stating_every_step(spec: OperationalSpec, ast: StrategyAst) -> OperationalSpec:
    """The spec with a criterion for every step of the strategy it leaves out.

    An edit is planned against the structure, so a live step the spec does not
    state is one the next edit removes without being asked to. The structure
    the spec holds is a plan: it gains the steps it leaves out, joined the way
    the strategy joins them, and keeps the operators and the nesting it
    states. A structure that names a criterion the strategy has not built is a
    plan the strategy has not reached, and it is left alone.
    """
    derived = spec_from_ast(ast, goal=spec.goal)
    built = {criterion.id for criterion in derived.criteria}
    if derived.structure is None or not structure_criteria(spec.structure) <= built:
        return spec
    stated = {criterion.id for criterion in spec.criteria}
    missing = [c for c in derived.criteria if c.id not in stated]
    if not missing:
        return spec
    framed: dict[frozenset[str], StructureNode] = {}
    if spec.structure is not None:
        _by_the_criteria_named(spec.structure.root, framed)
    reconciled = spec.model_copy(deep=True)
    reconciled.criteria = [*reconciled.criteria, *missing]
    reconciled.structure = SpecStructure(
        root=_holding_the_steps_left_out(
            derived.structure.root, framed, frozenset(c.id for c in missing)
        ),
    )
    return reconciled


def _by_the_criteria_named(
    node: StructureNode, found: dict[frozenset[str], StructureNode]
) -> None:
    """Index every node of a structure by the criteria it names, widest first."""
    found.setdefault(criteria_under(node), node)
    for child in node.inputs:
        _by_the_criteria_named(child, found)


def _holding_the_steps_left_out(
    node: StructureNode,
    framed: Mapping[frozenset[str], StructureNode],
    missing: frozenset[str],
) -> StructureNode:
    """The strategy's node, holding the framed shape wherever the spec states one.

    A subtree the spec states in full is the spec's own. A subtree that holds
    a step the spec leaves out follows the strategy, and keeps the strategy's
    operator unless the spec states a join over the same two sides.
    """
    under = criteria_under(node)
    left_out = under & missing
    if not left_out:
        return framed.get(under, node)
    inputs = [_holding_the_steps_left_out(c, framed, missing) for c in node.inputs]
    stated = framed.get(under - left_out)
    operator = (
        stated.operator
        if stated is not None and _joins_the_same_sides(stated, node, missing)
        else node.operator
    )
    return node.model_copy(update={"inputs": inputs, "operator": operator})


def _joins_the_same_sides(
    stated: StructureNode, node: StructureNode, missing: frozenset[str]
) -> bool:
    """The spec joins the sides this node of the strategy joins.

    A node above the framed join names the same criteria once the left-out
    steps are taken away, so the sides are compared as well as the set.
    """
    if stated.kind != "combine" or len(stated.inputs) != len(node.inputs):
        return False
    return all(
        criteria_under(side) == criteria_under(branch) - missing
        for side, branch in zip(stated.inputs, node.inputs, strict=True)
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
    criteria = [
        criterion
        if criterion.search_name not in sheet_params
        else criterion.model_copy(
            update={
                "resolved_params": {
                    name: value
                    for name, value in criterion.resolved_params.items()
                    if name in sheet_params[criterion.search_name]
                }
            }
        )
        for criterion in spec.criteria
    ]
    return spec.model_copy(update={"criteria": criteria})
