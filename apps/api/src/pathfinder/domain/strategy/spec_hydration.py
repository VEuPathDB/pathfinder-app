"""Reconstruct an OperationalSpec from a strategy that already exists.

The graph editor, a saved-strategy import and every thread whose checkpoint was
flushed own a strategy no spec describes. The persisted AST holds the searches
and the bound parameter values, so the spec is derived rather than re-asked.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import NamedTuple

from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
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
from pathfinder.domain.strategy.step_words import StepWords

__all__ = [
    "analysis_criteria_stated",
    "criterion_analysing",
    "hidden_params_dropped",
    "root_join_operator",
    "sheet_bound",
    "spec_from_ast",
    "spec_stating_the_live_tree",
]

Analyses = Mapping[str, AnalysisBinding]
_NO_ANALYSES: Analyses = {}
_SYMMETRIC = frozenset({CombineOp.INTERSECT, CombineOp.UNION})


def spec_from_ast(
    ast: StrategyAst, *, goal: str, analyses: Analyses = _NO_ANALYSES
) -> OperationalSpec:
    """Reconstruct the spec a strategy would have had.

    One criterion per non-combine node, keyed on the node's step id, holding
    the parameters the node carries. A step ``analyses`` reads as an exported
    analysis is stated by that binding instead. The structure mirrors the
    tree. The criterion text is the researcher's words the strategy stored for
    the step, else its label, so no code may derive a value from it.
    """
    seed_id = _deepest_primary_leaf(ast.root).id
    criteria: list[Criterion] = []
    words = StepWords.of(ast).criterion_texts
    structure = _structure_of(ast.root, _Reading(seed_id, criteria, words, analyses))
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
    analyses: Analyses = _NO_ANALYSES,
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
    derived = spec_from_ast(ast, goal=spec.goal, analyses=analyses)
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
    hanging = _hanging_at_the_root(structure, pending)
    if structure is None or hanging is None:
        return None
    return StructureNode(
        kind="combine",
        operator=structure.root.operator,
        inputs=[built_root, *hanging],
    )


def _hanging_at_the_root(
    structure: SpecStructure | None, pending: Collection[str]
) -> list[StructureNode] | None:
    """The leaves of these criteria when each is an input of the root combine."""
    if structure is None or structure.root.kind != "combine":
        return None
    hanging = [
        node
        for node in structure.root.inputs
        if node.kind == "leaf" and node.criterion_id in pending
    ]
    if {node.criterion_id for node in hanging} != set(pending):
        return None
    return hanging


def root_join_operator(
    structure: SpecStructure | None, criterion_id: str
) -> CombineOp | None:
    """The operator that joins a step for this leaf to the strategy's root.

    The leaf is an input of the root combine, and the join puts it after the
    root, so an operator that reads its inputs in order needs the leaf last.
    None when the structure places the leaf anywhere else.
    """
    if structure is None or _hanging_at_the_root(structure, [criterion_id]) is None:
        return None
    root = structure.root
    operator = root.operator
    if operator is None:
        return None
    if operator in _SYMMETRIC or root.inputs[-1].criterion_id == criterion_id:
        return operator
    return None


def _deepest_primary_leaf(node: StrategyStepNode) -> StrategyStepNode:
    """The step at the bottom of the primary-input chain."""
    while node.primary_input is not None:
        node = node.primary_input
    return node


class _Reading(NamedTuple):
    """What a hydration reads each node against, and the criteria it states."""

    seed_id: str
    criteria: list[Criterion]
    words: Mapping[str, str]
    analyses: Analyses


def _structure_of(node: StrategyStepNode, reading: _Reading) -> StructureNode:
    kind = node.infer_kind()
    inputs = [_structure_of(child, reading) for child in node.inputs()]
    if kind == "combine":
        return StructureNode(kind="combine", operator=node.operator, inputs=inputs)
    stated = Criterion(
        id=node.id,
        text=(
            reading.words.get(node.id)
            or node.display_name
            or f"{node.search_name} step"
        ),
        search_name=node.search_name,
        role=_role_of(node.id, kind, reading.seed_id),
        resolved_params=dict(node.parameters),
    )
    binding = reading.analyses.get(node.id)
    if binding is not None:
        stated = criterion_analysing(stated, node.search_name, binding).model_copy(
            update={"text": binding.words}
        )
    reading.criteria.append(stated)
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


def criterion_analysing(
    criterion: Criterion, search_name: str, binding: AnalysisBinding
) -> Criterion:
    """The criterion stated by the analysis its step exports, and nothing else.

    The document lives on the binding, so no value of it is a parameter the
    criterion states, defaults, asks for or explains.
    """
    return criterion.model_copy(
        update={
            "search_name": search_name,
            "saved_strategy_ref": None,
            "analysis": binding,
            "needs_analysis_on": None,
            "resolved_params": {},
            "defaulted_params": [],
            "open_params": [],
            "assumptions": [],
            "alternatives": [],
        }
    )


def analysis_criteria_stated(
    spec: OperationalSpec, analyses: Analyses
) -> OperationalSpec:
    """The spec with every exported analysis stated by its binding.

    A criterion whose step reads as an export and states no binding gains the
    one its step reads as. A drop recorded on an analysis dataset leaves when
    an export on that dataset answered it, and otherwise becomes a criterion
    waiting for that analysis, joined at the root under INTERSECT, the join
    such a drop was built at. One criterion waits per dataset, so a second
    drop on it folds into the first. A spec with neither is returned as is.
    """
    unbound = {c.id for c in spec.criteria if c.analysis is None and c.id in analyses}
    answered = {binding.dataset_id for binding in analyses.values()}
    carried = [drop for drop in spec.dropped if drop.eda_dataset_id is not None]
    waiting = [drop for drop in carried if drop.eda_dataset_id not in answered]
    if not unbound and not carried:
        return spec
    stated = spec.model_copy(deep=True)
    stated.criteria = [
        criterion_analysing(c, c.search_name, analyses[c.id]) if c.id in unbound else c
        for c in stated.criteria
    ]
    for drop in waiting:
        criterion = Criterion(
            id=f"c_{drop.eda_dataset_id}",
            text=drop.text,
            needs_analysis_on=drop.eda_dataset_id,
        )
        if any(c.id == criterion.id for c in stated.criteria):
            continue
        stated.criteria.append(criterion)
        stated.structure = _joined_at_the_root(stated.structure, criterion.id)
    stated.dropped = [drop for drop in stated.dropped if drop.eda_dataset_id is None]
    return stated


def _joined_at_the_root(
    structure: SpecStructure | None, criterion_id: str
) -> SpecStructure:
    leaf = StructureNode(kind="leaf", criterion_id=criterion_id)
    if structure is None:
        return SpecStructure(root=leaf)
    root = structure.root
    if root.kind == "combine" and root.operator is CombineOp.INTERSECT:
        return SpecStructure(
            root=root.model_copy(update={"inputs": [*root.inputs, leaf]})
        )
    return SpecStructure(
        root=StructureNode(
            kind="combine", operator=CombineOp.INTERSECT, inputs=[root, leaf]
        )
    )
