"""Folding the bound criteria into the strategy tree."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.combination_check import first_combination_violation
from pathfinder.domain.strategy.operational_spec import SpecStructure, StructureNode


class SetStructureResult(CamelModel):
    """Result of folding the bound criteria into the strategy structure."""

    criteria_combined: int


def _count_criteria(node: StructureNode) -> int:
    own = 1 if node.criterion_id else 0
    return own + sum(_count_criteria(child) for child in node.inputs)


def _refuse_a_tree_that_breaks_a_stated_combination(
    state: AgentToolState, proposed: SpecStructure
) -> None:
    """Reject a tree that answers a different question than the user asked.

    The check abstains when a requirement states no single operator, or when
    its terms name no distinct criteria of the draft.
    """
    breach = first_combination_violation(
        state.combination_requirements,
        state.operational_spec_draft.criteria,
        proposed,
    )
    if breach is None:
        return
    msg = (
        f"The structure is refused: {breach.message}. Restate the tree so "
        f"those criteria sit under one {breach.required.value} branch, and "
        f"combine that branch with the rest."
    )
    raise ModelRetry(msg)


async def set_structure(
    ctx: RunContext[AgentDeps],
    *,
    root: StructureNode,
) -> ToolReturn[SetStructureResult]:
    """Set the strategy tree from the bound criteria.

    ``root`` is a tree, not a list, because the shape carries meaning. Each
    node is one of:

    - ``{"kind": "leaf", "criterionId": "<id>"}`` -- one bound criterion.
    - ``{"kind": "combine", "operator": "INTERSECT" | "UNION" | "MINUS",
      "inputs": [<left>, <right>]}`` -- boolean-combine two subtrees.
    - ``{"kind": "transform", "criterionId": "<id>", "inputs": [<subtree>]}``
      -- a search that MAPS the subtree's genes rather than combining with
      them (e.g. ``GenesByOrthologs`` returning orthologs in another
      organism). It is wired to that input, never run standalone.

    Nest freely. When a property has several alternative evidence sources,
    UNION them into their own branch and INTERSECT that branch with the
    others -- do not flatten it into a chain, which asks a different
    question. WDK step trees carry a primary and a secondary input, so a
    branch on either side is representable. A combination the user stated is
    checked here: a tree that joins those criteria with another operator is
    refused.
    """
    proposed = SpecStructure(root=root)
    _refuse_a_tree_that_breaks_a_stated_combination(ctx.deps.agent_state, proposed)
    ctx.deps.agent_state.frame_set_structure(proposed)
    combined = _count_criteria(root)
    return with_summary(
        SetStructureResult(criteria_combined=combined),
        f"Structure set: {combined} criteria",
        ctx=ctx,
    )
