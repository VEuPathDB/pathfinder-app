"""The Lead's own tools: memory, gene sets, clears and deletes."""

from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb import JSONObject

from pathfinder.ai.lead._delete_rules import DeleteSurface
from pathfinder.ai.lead.answered_strategy import the_strategy_now_answers_to
from pathfinder.ai.lead.card_reply import CardReply
from pathfinder.ai.lead.deleted_steps import named_step
from pathfinder.ai.lead.dispatch_context import inner_context
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import (
    conversation,
    export,
    gene_sets,
    strategy_edits,
)
from pathfinder.ai.tools.standalone.conversation_models import ClearStrategyResult
from pathfinder.ai.tools.standalone.export_models import ExportResultResponse
from pathfinder.ai.tools.standalone.gene_set_models import (
    GeneSetCreatedResponse,
    GeneSetListResponse,
)
from pathfinder.services.strategies.graph_outcome import live_outcome


async def save_gene_set(
    ctx: RunContext[LeadDeps],
    name: str,
    step_id: str | None = None,
    gene_ids: list[str] | None = None,
) -> ToolReturn[GeneSetCreatedResponse]:
    """Save a gene set the user can export and publish.

    This is the save the user asks for when they say "save these genes as a
    gene set". The set appears in the conversation, and its id is what the export
    tools take. ``remember`` stores a note about a set; it creates none.
    Controls are saved with ``build_control_set``, never as a gene set.

    Args:
        name: The name the user gave the set.
        step_id: The step of THIS conversation's strategy whose genes to save,
            by its graph id (e.g. 'step_3'). Leave it out for the strategy's
            root step. The genes of a step are read from that step on
            VEuPathDB, and its WDK ids come from the strategy; never type one.
        gene_ids: A list of gene IDs the user pasted or this turn computed,
            which no step holds. It saves that list alone, so leave it out
            whenever the genes are a step's.
    """
    return await gene_sets.save_gene_set(
        inner_context(ctx),
        name=name,
        step_id=step_id,
        gene_ids=gene_ids,
    )


async def list_gene_sets(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[GeneSetListResponse]:
    """List the gene sets the user saved on this site, each with its id.

    Call it before you use a gene-set id you did not just create, and when a
    tool answers that an id names nothing.
    """
    return await gene_sets.list_gene_sets(inner_context(ctx))


async def export_gene_set(
    ctx: RunContext[LeadDeps],
    gene_set_id: str,
    output_format: str = "csv",
) -> ToolReturn[ExportResultResponse]:
    """Export a saved gene set as a downloadable CSV or TXT file.

    This is the download the user asks for when they name a set they saved.
    Take the id from ``list_gene_sets``. The reply carries
    the link, which expires after ten minutes, so give it to the user.

    Args:
        gene_set_id: The gene set to export.
        output_format: Export format: csv or txt.
    """
    return await export.export_gene_set(
        inner_context(ctx),
        gene_set_id=gene_set_id,
        output_format=output_format,
    )


async def clear_the_strategy(
    ctx: RunContext[LeadDeps], *, keep_control_sets: bool
) -> ToolReturn[ClearStrategyResult]:
    """Clear every step and set its request aside, and the control sets unless kept."""
    inner = inner_context(ctx)
    cleared = await conversation.clear_strategy(inner, confirm=True)
    state = ctx.deps.state
    state.turn_markers.edited = True
    # This message's own request is what the next pass frames.
    state.domain.set_the_cleared_strategy_aside(keep_control_sets=keep_control_sets)
    intent = ctx.deps.intent
    if intent is not None and state.turn_markers.intent_classified:
        state.domain.record_intent(intent, request_text=state.user_prompt)
    the_strategy_now_answers_to(state, None, None)
    return cleared


async def clear_strategy(
    ctx: RunContext[LeadDeps],
    *,
    reply: CardReply,
    confirm: bool,
) -> ToolReturn[ClearStrategyResult]:
    """Throw the whole strategy away so the user can start over.

    This is the ONLY deliberate destructive path. Use it when the user asks to
    scrap the strategy and begin again, and never as a way around
    ``build_strategy``'s refusal on a conversation that already has one: a request
    that changes what the strategy asks is ``edit_strategy``.

    Every step goes from this conversation, and the next build creates a strategy of
    its own on VEuPathDB instead of reusing the one that stood here. The
    cleared state appends a revision, so a revert restores what this call
    cleared. The user approves the call on its card; ``reply`` streams above
    the card and says what goes. After it returns, frame and build afresh.

    ``confirm`` must be true; the call is refused otherwise.
    """
    del reply
    if not confirm:
        return await conversation.clear_strategy(inner_context(ctx), confirm=False)
    return await clear_the_strategy(ctx, keep_control_sets=False)


async def delete_step(
    ctx: RunContext[LeadDeps],
    step_id: str,
    *,
    reply: CardReply,
) -> ToolReturn[JSONObject]:
    """Remove one step from the strategy.

    This is how a step the user wants gone leaves: a step they say is wrong, a
    step left over from an earlier turn, or a step standing outside the
    strategy. What leaves with it is the graph's own answer, and the call
    reports it: a step under a combine takes that combine with it and its
    sibling takes their place; a step under a transform takes that transform
    with it; a transform leaves alone and the step it consumed takes its
    place; the strategy's root, when it is a combine, leaves with its
    secondary branch and the primary branch becomes the root; any other root
    leaves with every step under it. A delete no re-wiring of the graph
    performs is refused with the reason, as is any root of more than one step
    on a conversation that holds several roots and no push says which is the
    strategy - name a step under the one you mean instead. The write appends a
    revision, so a revert restores what it removed, and the user approves the
    call on its card, which lists every step the graph says goes. ``reply``
    streams above the card and promises no step of them stays.

    Args:
        step_id: The step to remove, by the id the strategy graph shows.
        reply: Your reply, which the researcher reads above the card.
    """
    del reply
    inner = inner_context(ctx)
    session = ctx.deps.runtime.strategy_session
    before = session.get_graph(None)
    held = {} if before is None else dict(before.steps)
    deleted = await strategy_edits.delete_the_step(
        inner, step_id, surface=DeleteSurface.LEAD
    )
    after = session.get_graph(None)
    ctx.deps.state.turn_markers.deleted_steps.extend(
        named_step(node)
        for held_id, node in held.items()
        if after is None or held_id not in after.steps
    )
    ctx.deps.state.turn_markers.edited = True
    domain = ctx.deps.state.domain
    framed = domain.operational_spec
    if framed is not None:
        domain.operational_spec = inner.deps.agent_state.operational_spec_draft
        remaining = (
            [] if domain.operational_spec is None else domain.operational_spec.criteria
        )
        kept = {c.id for c in remaining}
        domain.retire_what_a_delete_leaves_unanswered(
            [c for c in framed.criteria if c.id not in kept], remaining
        )
    the_strategy_now_answers_to(
        ctx.deps.state,
        ctx.deps.state.domain.operational_spec,
        ctx.deps.runtime.strategy_session.get_graph(None),
    )
    if ctx.deps.state.domain.last_build_outcome is not None:
        ctx.deps.state.record_resync(live_outcome(session))
    return deleted
