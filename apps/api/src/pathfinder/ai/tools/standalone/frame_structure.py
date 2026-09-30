"""Folding the bound criteria into the strategy tree."""

from __future__ import annotations

from collections.abc import Iterator

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp.catalog import get_raw_record_types
from veupathdb_mcp.gene_lookup import list_organisms

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.combination_check import (
    first_combination_violation,
    unstated_union,
)
from pathfinder.domain.strategy.operational_spec import (
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.organism_scope import organism_params_of, universe_key
from pathfinder.domain.strategy.orthology import (
    copy_refusal,
    round_trip_refusal,
    stated_steps,
)
from pathfinder.domain.strategy.spec_duplicates import (
    DuplicateDrop,
    fold_duplicate_inputs,
)
from pathfinder.domain.strategy.spec_fold import (
    FoldedStructure,
    OrganismDrop,
    fold_organism_universe,
    intersected_leaves,
)
from pathfinder.domain.strategy.validate import (
    first_cross_organism_refusal,
    transform_input_refusal,
)
from pathfinder.domain.strategy.words import words_of
from pathfinder.services.strategies.organism_universe import universe_counts
from pathfinder.services.strategies.record_classes import (
    record_class_names,
    search_record_classes,
)


class StructureDrop(CamelModel):
    """An input a structure fold removed, and what became of its text."""

    criterion_id: str
    met: bool
    fate: str

    @classmethod
    def of(cls, drop: OrganismDrop | DuplicateDrop) -> StructureDrop:
        return cls(criterion_id=drop.criterion_id, met=drop.met, fate=drop.fate)


class SetStructureResult(CamelModel):
    """Result of folding the bound criteria into the strategy structure."""

    criteria_combined: int
    dropped: list[StructureDrop] = Field(default_factory=list)


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


def _refuse_a_union_no_one_stated(
    state: AgentToolState, proposed: SpecStructure, held: frozenset[str]
) -> None:
    """A UNION that adds an arm to the strategy's own steps changes the
    researcher's answer, so it stands only on a stated OR over its arms."""
    found = unstated_union(
        proposed,
        held,
        state.combination_requirements,
        state.operational_spec_draft.criteria,
    )
    if found is None:
        return
    msg = (
        f"The structure is refused: a UNION joins {', '.join(found.held)}, which "
        f"the strategy holds, to {', '.join(found.added)}, which this turn adds, "
        f"and the researcher stated no alternative that joins them. A UNION "
        f"changes the researcher's result. A question that compares two counts "
        f"is answered by the Lead's compare_search_variants and adds no step. "
        f"Join the new criteria as the request says, or leave them out of the "
        f"tree; when the request is ambiguous, end needs_user with a Drop/Keep "
        f"question on the new criteria."
    )
    raise ModelRetry(msg)


def _refuse_a_tree_that_leaves_out_an_analysis(
    state: AgentToolState, proposed: SpecStructure
) -> None:
    """A tree names every analysis criterion, bound or waiting for its analysis.

    Such a criterion is realized by the Lead's EDA tools and never by a search
    this pass binds, so a tree without it loses the comparison.
    """
    named = structure_criteria(proposed)
    left_out = [
        c.id
        for c in state.operational_spec_draft.criteria
        if (c.analysis is not None or c.pending_analysis) and c.id not in named
    ]
    if not left_out:
        return
    msg = (
        f"The structure leaves out {left_out}, which the analysis workflow "
        f"realizes. Put each of them in the tree where the request places it; "
        f"no other criterion stands for it."
    )
    raise ModelRetry(msg)


def _refuse_a_tree_the_site_cannot_run(
    state: AgentToolState, proposed: SpecStructure
) -> None:
    """A copy restates a subtree the tree holds, a round trip keeps the source,
    and an INTERSECT joins genes of one organism."""
    stated = state.operational_spec_draft.model_copy(update={"structure": proposed})
    steps = stated_steps(stated)
    marked = organism_params_of(stated.criteria)
    refusal = (
        copy_refusal(proposed.root)
        or round_trip_refusal(stated)
        or (None if steps is None else first_cross_organism_refusal(steps, marked))
    )
    if refusal is not None:
        msg = f"The structure is refused: {refusal} Nothing was recorded."
        raise ModelRetry(msg)


async def _refuse_a_transform_over_another_record_class(
    ctx: RunContext[AgentDeps], proposed: SpecStructure
) -> None:
    """A transform runs only on an input of a record class WDK says it takes.

    The site is read only when the tree holds a transform.
    """
    if all(kind != "transform" for _, kind in _criterion_nodes(proposed.root)):
        return
    draft = ctx.deps.agent_state.operational_spec_draft
    stated = draft.model_copy(update={"structure": proposed})
    steps = stated_steps(stated)
    if steps is None:
        return
    named = structure_criteria(proposed)
    searches = [c.search_name for c in stated.criteria if c.id in named]
    refusal = transform_input_refusal(
        steps,
        await search_record_classes(ctx.deps.site_id, searches),
        await record_class_names(ctx.deps.site_id),
    )
    if refusal is not None:
        msg = f"The structure is refused: {refusal} Nothing was recorded."
        raise ModelRetry(msg)


def _criterion_nodes(node: StructureNode) -> Iterator[tuple[str, str]]:
    if node.criterion_id:
        yield node.criterion_id, node.kind
    for child in node.inputs:
        yield from _criterion_nodes(child)


def _refuse_a_node_the_role_contradicts(
    state: AgentToolState, proposed: SpecStructure
) -> None:
    """A criterion runs on an input step or it runs alone, and the tree says which."""
    by_id = {crit.id: crit for crit in state.operational_spec_draft.criteria}
    for criterion_id, kind in _criterion_nodes(proposed.root):
        criterion = by_id.get(criterion_id)
        if criterion is None:
            continue
        if kind == "transform" and criterion.role != "transform":
            msg = (
                f"{criterion.id} is bound to {criterion.search_name}, which takes no "
                f"input step, so it cannot be a transform node. Make it a leaf, or "
                f"bind the criterion to a search that takes an input step."
            )
            raise ModelRetry(msg)
        if kind == "leaf" and criterion.role == "transform":
            msg = (
                f"{criterion.id} is bound to {criterion.search_name}, which runs on a "
                f"previous step, so it cannot be a leaf. Wire it as a transform node "
                f"over the subtree it maps."
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
      organism). It is wired to that input, never run standalone, and the
      input returns a record class the transform declares it takes.
    - ``{"kind": "copy", "inputs": [<subtree>]}`` -- a subtree this tree
      already states, node for node, stated again. It is the only place a
      criterion appears twice; the pass states it as criteria of its own.
      An orthology round trip keeps the source genes only as the source
      INTERSECT a transform back over a transform out over a copy of the
      source, with one synteny value on both transforms.

    Nest freely. When a property has several alternative evidence sources,
    UNION them into their own branch and INTERSECT that branch with the
    others -- do not flatten it into a chain, which asks a different
    question. WDK step trees carry a primary and a secondary input, so a
    branch on either side is representable. A combination the user stated is
    checked here: a tree that joins those criteria with another operator is
    refused. A UNION that joins a step the strategy holds to a criterion this
    turn adds is refused unless the researcher stated that OR. An INTERSECT
    input that states only the organism another input already runs on,
    matches every gene of it, or repeats another input's searches and values,
    is dropped, and ``dropped`` says what became of its text.
    """
    state = ctx.deps.agent_state
    proposed = SpecStructure(root=root)
    graph = ctx.deps.strategy_session.get_graph(None)
    live = frozenset(graph.steps) if graph is not None else frozenset[str]()
    _refuse_a_tree_that_breaks_a_stated_combination(state, proposed)
    _refuse_a_union_no_one_stated(state, proposed, live)
    _refuse_a_node_the_role_contradicts(state, proposed)
    _refuse_a_tree_that_leaves_out_an_analysis(state, proposed)
    _refuse_a_tree_the_site_cannot_run(state, proposed)
    await _refuse_a_transform_over_another_record_class(ctx, proposed)
    deduped = fold_duplicate_inputs(
        state.operational_spec_draft, proposed, live_step_ids=live
    )
    folded = (await _organism_folded(ctx, deduped.structure, live)).holding_open(
        state.stated_requirements, state.request_messages
    )
    dropped: list[OrganismDrop | DuplicateDrop] = [*deduped.dropped, *folded.dropped]
    state.frame_set_structure(folded.structure)
    for drop in dropped:
        state.frame_drop_criterion(
            drop.criterion_id, drop.fate, requirement=drop.requirement
        )
    combined = len(structure_criteria(folded.structure))
    summary = f"Structure set: {combined} {'search' if combined == 1 else 'searches'}"
    return with_summary(
        SetStructureResult(
            criteria_combined=combined,
            dropped=[StructureDrop.of(drop) for drop in dropped],
        ),
        "; ".join([summary, *(f"dropped {d.criterion_id}" for d in dropped)]),
        ctx=ctx,
    )


async def _organism_folded(
    ctx: RunContext[AgentDeps], proposed: SpecStructure, live: frozenset[str]
) -> FoldedStructure:
    """The tree with each input that states only a sibling's organism dropped.

    The site is read only when an INTERSECT input is a bound criterion that
    marks an organism parameter and is no live step, and an organism's genes
    are counted only for such an input whose binding sets only the organism.
    """
    state = ctx.deps.agent_state
    draft = state.operational_spec_draft
    named = intersected_leaves(proposed.root) - live
    candidates = [c for c in draft.criteria if c.id in named and c.organism_param]
    if not candidates:
        return FoldedStructure(structure=proposed)
    record_types = {
        c.id: overview.record_type
        for c in candidates
        if (overview := state.get_overview(c.search_name)) is not None
    }
    record_words = [
        word
        for record in await get_raw_record_types(ctx.deps.site_id)
        if record.url_segment in record_types.values()
        for name in (
            record.display_name,
            record.display_name_plural,
            record.short_display_name,
        )
        for word in words_of(name)
    ]
    organisms = await list_organisms(ctx.deps.site_id)
    counts: dict[str, int] = {}
    for record_type in sorted(set(record_types.values())):
        keyed = {
            c.id: key
            for c in candidates
            if record_types.get(c.id) == record_type
            and (key := universe_key(c, organisms)) is not None
        }
        counted = await universe_counts(
            ctx.deps.site_id, record_type, list(keyed.values())
        )
        counts.update(
            {cid: counted[key] for cid, key in keyed.items() if key in counted}
        )
    return fold_organism_universe(
        draft, proposed, organisms, record_words, counts, live_step_ids=live
    )
