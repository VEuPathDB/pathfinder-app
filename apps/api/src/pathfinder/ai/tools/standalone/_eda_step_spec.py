"""How an exported EDA step is stated in the operational spec."""

from __future__ import annotations

from pydantic_ai import RunContext
from veupathdb.domain.parameters import to_wire
from veupathdb.domain.strategy import StrategyStepNode, subtree_ids
from veupathdb_mcp.catalog import EDA_DATASET_ID_PARAM

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import contradicted_joins
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps


def criterion_note(ctx: RunContext[LeadDeps], step_id: str) -> str:
    """The criterion a step answers, as a parenthetical, or nothing."""
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return ""
    stated = [c.text for c in spec.criteria if c.id == step_id]
    return f" ({stated[0]})" if stated else ""


def _exported_criterion(node: StrategyStepNode) -> Criterion:
    """The criterion the exported step answers."""
    return Criterion(
        id=node.id,
        text=node.display_name or "the open EDA analysis",
        search_name=node.search_name,
        resolved_params=dict(node.parameters),
        confidence=1.0,
    )


def answered_drop_cleared(spec: OperationalSpec, node: StrategyStepNode) -> None:
    """Take the criteria this export answers out of the spec's drops.

    A drop states an EDA criterion nothing in the strategy realizes, so only
    an export the strategy holds answers one.
    """
    dataset = node.parameters.get(EDA_DATASET_ID_PARAM)
    if dataset is None:
        return
    exported = to_wire(dataset)
    spec.dropped = [d for d in spec.dropped if d.eda_dataset_id != exported]


def state_the_exported_step(
    ctx: RunContext[LeadDeps], graph: StrategyGraph, node: StrategyStepNode
) -> None:
    """State the exported step as a criterion of the spec, in its own place.

    A step wired into the main tree is one the strategy states, so a later
    write is measured against it like any other criterion. A step outside that
    tree is stated by nothing, which is how a detached root is represented.
    """
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return
    root_id = graph.primary_root_id()
    if root_id is None or node.id not in subtree_ids(root_id, graph.steps):
        return
    answered_drop_cleared(spec, node)
    ctx.deps.state.domain.record_criterion(_exported_criterion(node))


def structure_the_graph_states(graph: StrategyGraph, goal: str) -> SpecStructure | None:
    """The structure a build would state for the strategy the graph holds."""
    ast = graph.to_strategy_ast()
    return None if ast is None else spec_from_ast(ast, goal=goal).structure


def structure_states_the_graph(ctx: RunContext[LeadDeps], graph: StrategyGraph) -> bool:
    """Whether the spec's structure states the strategy the graph holds.

    Every criterion it names answers to a step, and it joins them at the
    operators the graph carries. Anything else is a plan the strategy has
    still to reach, and an export does not restate a plan.
    """
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return False
    named = structure_criteria(spec.structure)
    if not named or not named <= set(graph.steps):
        return False
    return not contradicted_joins(spec.structure, graph, named)


def restate_the_structure(ctx: RunContext[LeadDeps], graph: StrategyGraph) -> None:
    """Restate the spec's structure as the one the live strategy holds."""
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return
    spec.structure = structure_the_graph_states(graph, spec.goal)


def spec_after_the_replacement(
    ctx: RunContext[LeadDeps],
    graph: StrategyGraph,
    node: StrategyStepNode,
    replace_step_id: str,
) -> OperationalSpec | None:
    """The spec with the export in the place the replaced steps held.

    A write is measured against the criteria the spec states, so the spec the
    write is measured against already names the step it produces.
    """
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return None
    departed = set(subtree_ids(replace_step_id, graph.steps))
    if replace_step_id in structure_criteria(spec.structure):
        restated = _restated(spec, node, replace_step_id, departed)
        answered_drop_cleared(restated, node)
        return restated
    reconciled = spec_without_steps(spec, departed)
    root_id = graph.primary_root_id()
    if root_id is None or replace_step_id not in subtree_ids(root_id, graph.steps):
        return reconciled
    answered_drop_cleared(reconciled, node)
    reconciled.criteria = [c for c in reconciled.criteria if c.id != node.id]
    reconciled.criteria.append(_exported_criterion(node))
    return reconciled


def _restated(
    spec: OperationalSpec,
    node: StrategyStepNode,
    replace_step_id: str,
    departed: set[str],
) -> OperationalSpec:
    """The spec whose structure names the export where it named the old step."""
    restated = spec.model_copy(deep=True)
    if restated.structure is not None:
        restated.structure = SpecStructure(
            root=_node_restated(restated.structure.root, replace_step_id, node.id),
        )
    exported = _exported_criterion(node)
    restated.criteria = [
        exported if c.id == replace_step_id else c
        for c in restated.criteria
        if c.id == replace_step_id or c.id not in departed
    ]
    restated.open_slots = [
        slot for slot in restated.open_slots if slot.criterion_id not in departed
    ]
    return restated


def _node_restated(
    node: StructureNode, replace_step_id: str, exported_id: str
) -> StructureNode:
    """The structure with the export standing for the replaced node.

    The export is one leaf, so it stands for the whole subtree that node held.
    """
    if node.kind != "combine" and node.criterion_id == replace_step_id:
        return StructureNode(kind="leaf", criterion_id=exported_id)
    return node.model_copy(
        update={
            "inputs": [
                _node_restated(child, replace_step_id, exported_id)
                for child in node.inputs
            ],
        },
    )
