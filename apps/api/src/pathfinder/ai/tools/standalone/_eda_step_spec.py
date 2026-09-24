"""How an exported EDA step is stated in the operational spec: by the analysis
binding it carries, in the place the spec or the strategy gives it."""

from __future__ import annotations

from pydantic_ai import RunContext
from veupathdb.domain.strategy import StrategyStepNode, subtree_ids

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import contradicted_joins
from pathfinder.domain.strategy.spec_hydration import (
    criterion_analysing,
    spec_from_ast,
)
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps
from pathfinder.domain.strategy.spec_tree import (
    renumber_criteria,
)


def criterion_note(ctx: RunContext[LeadDeps], step_id: str) -> str:
    """The criterion a step answers, as a parenthetical, or nothing."""
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return ""
    stated = [c.text for c in spec.criteria if c.id == step_id]
    return f" ({stated[0]})" if stated else ""


def _exported_criterion(node: StrategyStepNode, binding: AnalysisBinding) -> Criterion:
    """The criterion the exported step is: its binding, in the binding's words."""
    return criterion_analysing(
        Criterion(id=node.id, text=binding.words, confidence=1.0),
        node.search_name,
        binding,
    )


def state_the_exported_step(
    ctx: RunContext[LeadDeps],
    graph: StrategyGraph,
    node: StrategyStepNode,
    binding: AnalysisBinding,
) -> None:
    """State the exported step as a criterion of the spec, in its own place.

    A step wired into the main tree is one the strategy states, so a later
    write is measured against it like any other criterion. A step outside that
    tree is stated by nothing, which is how a detached root is represented. A
    thread whose spec states no criterion states the tree the export now roots.
    """
    domain = ctx.deps.state.domain
    root_id = graph.primary_root_id()
    if root_id is None or node.id not in subtree_ids(root_id, graph.steps):
        return
    spec = domain.operational_spec
    ast = graph.to_strategy_ast()
    if (spec is None or not spec.criteria) and ast is not None:
        stated_goal = "" if spec is None else spec.goal
        domain.operational_spec = spec_from_ast(
            ast,
            goal=stated_goal or ctx.deps.state.request_the_thread_answers,
            analyses={node.id: binding},
        )
        return
    domain.record_criterion(_exported_criterion(node, binding))


def spec_binding_the_export(
    spec: OperationalSpec,
    criterion_id: str,
    node: StrategyStepNode,
    binding: AnalysisBinding,
) -> OperationalSpec:
    """The spec whose waiting criterion is the exported step, bound by its analysis.

    The criterion keeps the words the framing pass stated it in and takes the
    step's id, so the structure names the step where it named the criterion.
    """
    renumbered = renumber_criteria(spec, {criterion_id: node.id})
    renumbered.criteria = [
        criterion_analysing(c, node.search_name, binding) if c.id == node.id else c
        for c in renumbered.criteria
    ]
    return renumbered


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
    binding: AnalysisBinding,
) -> OperationalSpec | None:
    """The spec with the export in the place the replaced steps held.

    A write is measured against the criteria the spec states, so the spec the
    write is measured against already names the step it produces.
    """
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return None
    departed = set(subtree_ids(replace_step_id, graph.steps))
    exported = _exported_criterion(node, binding)
    if replace_step_id in structure_criteria(spec.structure):
        return _restated(spec, exported, replace_step_id, departed)
    reconciled = spec_without_steps(spec, departed)
    root_id = graph.primary_root_id()
    if root_id is None or replace_step_id not in subtree_ids(root_id, graph.steps):
        return reconciled
    reconciled.criteria = [c for c in reconciled.criteria if c.id != node.id]
    reconciled.criteria.append(exported)
    return reconciled


def _restated(
    spec: OperationalSpec,
    exported: Criterion,
    replace_step_id: str,
    departed: set[str],
) -> OperationalSpec:
    """The spec whose structure names the export where it named the old step."""
    restated = spec.model_copy(deep=True)
    if restated.structure is not None:
        restated.structure = SpecStructure(
            root=_node_restated(restated.structure.root, replace_step_id, exported.id),
        )
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
