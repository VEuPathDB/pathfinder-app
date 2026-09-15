"""The Lead's own tools: intent, memory, gene sets, live state and the ledger."""

from __future__ import annotations

from typing import Any, Literal

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb import JSONObject
from veupathdb_mcp.wdk.enrichment import EnrichmentAnalysisType

from pathfinder.ai.lead._delete_rules import DeleteSurface
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import inner_context
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.live_state import LiveStrategyState, read_live_state
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import (
    conversation,
    export,
    memory_tools,
    strategy_edits,
    workbench,
)
from pathfinder.ai.tools.standalone.conversation_models import ClearStrategyResult
from pathfinder.ai.tools.standalone.export_models import ExportResultResponse
from pathfinder.ai.tools.standalone.workbench import GENESET_ENRICHMENT
from pathfinder.ai.tools.standalone.workbench_models import (
    GeneSetCreatedResponse,
    GeneSetListResponse,
)
from pathfinder.domain.memory import MemoryKind
from pathfinder.platform.durable_worker import durable_agent_tool

LedgerSectionName = Literal["frame", "build", "verification"]


def classify_user_intent(
    ctx: RunContext[LeadDeps],
    intent: UserIntent,
) -> ToolReturn[UserIntent]:
    """Classify the user's intent for this turn. Call this exactly once,
    before any other sub-agent call.

    The message classified is this turn's own, which is pinned in your
    instructions; it is never passed here. Construct a ``UserIntent``
    with: ``classification`` (one of the IntentClassification enum
    values), ``inferred_goal`` (your one-sentence paraphrase),
    ``is_differential`` and ``differential_sides`` when the user is
    asking a comparison question, and any referenced step/strategy IDs.

    Populate ``explicit_constraints`` with one typed Constraint for every
    requirement the user STATES in this message - data type ("RNA-Seq
    only"), statistical threshold ("adjusted p <= 0.05"), fold change,
    comparator ("female vs male"), organism, record type, and percentile
    for a stated share ("top 10% expressed", "bottom quartile"), whose
    requested value carries the share and the direction. Capture their
    exact stated value. These override scoping's provisional assumptions
    for the same dimension, so a clarification answer like "RNA-Seq only,
    hard requirement" lands here even when scoping earlier assumed
    otherwise. Leave empty if the user states no concrete requirement.

    When the user says HOW their evidence lines combine - "A OR B",
    "either mass spec or DeRisi expression", "combine the two domain
    searches with a union", "both filters must hold" - add one constraint
    of kind "combination". Its requested value is that combination in the
    canonical form "<term> OR <term>" (or AND), with one term per line of
    evidence, written in the user's own words for it. Two terms minimum,
    one operator only: a request that mixes OR and AND is two
    constraints, one per group. Three or more terms state one flat group:
    every term joins at that operator, so evidence the user joins with the
    other operator belongs in a constraint of its own. This is the only
    machine-checkable record of the boolean shape they asked for, so a
    stated combination that never lands here is a strategy that can
    silently answer the other question.

    Set ``hard=True`` for non-negotiable requirements ("only", "must",
    "required", "do not use X"); set ``hard=False`` when the user states a
    PREFERENCE with an acceptable fallback ("RNA-Seq preferred, microarray
    fallback ok", "ideally X but Y is fine"). A soft constraint is surfaced
    but never blocks the turn if substituted.

    A message that answers a question you asked is
    ``clarification_response``, whatever else it carries: two answers
    followed by "go ahead and build it" is still the answer to them, and
    the request it answers is the one the thread is on. ``new_strategy``
    is for a message that ABANDONS that request and states a different
    one; the requirements the thread has stated are dropped when you say
    so, and are kept otherwise.

    Any other imperative asks for a build. "Run it", "rerun the compute",
    "build the strategy", "add those genes as a step", "create the step" -
    and a bare "yes, do it" that accepts an offer you made - are
    ``extend_strategy`` when the thread already has a strategy or an open
    analysis, and ``new_strategy`` when it has neither and answers no
    question of yours. A retry after a failed task is the same request
    again, so it keeps the classification that request had. None of them
    is a ``follow_up_question``: that value is for a message that asks you
    to EXPLAIN something and asks for no change to the data.

    Two classifications ask for no strategy at all:

    - ``context_statement``: the message states what the user works on and
      asks for nothing. No imperative, no question about the data. Example:
      "I'm investigating virulence factors in Leishmania major".
    - ``memory_request``: the message asks you to keep something for later.
      Example: "Please remember for future sessions: I always work with
      P. falciparum 3D7 and I prefer the Su et al. strand-specific dataset."

    Both are answered in prose, and ``memory_request`` with one ``remember``
    call per thing to keep. Neither is a request to build.

    PathFinder does its work through these tools; it writes no code and no
    general text. In scope: building, extending, editing and verifying
    strategies; enrichment; EDA; exports; workbench gene sets; memory;
    questions about the databases, the searches, the parameters and the
    organisms; and the biology behind a search - what a kinase is, what a
    signal peptide is, what a p-value cutoff means here. ``off_topic`` is the
    rest: code in any language, prose or email drafting, translation, general
    knowledge, and any message that names no VEuPathDB object, gene, organism,
    dataset or analysis. A borderline message that carries a real biological
    question is in scope. An ``off_topic`` turn reaches no tool after this one
    and answers in two sentences, so a message the tools can answer is never
    one.
    """
    ctx.deps.intent = intent
    ctx.deps.state.turn_markers.intent_classified = True
    ctx.deps.state.domain.record_intent(
        intent,
        request_text=ctx.deps.state.user_prompt,
    )
    return with_summary(
        intent,
        f"Intent: {intent.classification.value}",
        ctx=ctx,
    )


async def remember(
    ctx: RunContext[LeadDeps],
    kind: MemoryKind,
    name: str,
    summary: str,
    content: dict[str, object],
    tags: list[str] | None = None,
) -> ToolReturn[str]:
    """Store one thing the user asked you to keep for future sessions.

    Use it for a stated preference (a default organism, a preferred dataset)
    and for a fact they taught you. One call per thing remembered. Storing a
    preference is the whole answer to that request: do not build a strategy to
    "validate" it.

    It stores a note. A gene set the user asks you to save is created with
    ``create_workbench_gene_set``, and ``gene_set_note`` is a note about a set
    that already exists.
    """
    inner = inner_context(ctx)
    return await memory_tools.remember(
        inner,
        kind=kind,
        name=name,
        summary=summary,
        content=content,
        tags=tags,
    )


async def create_workbench_gene_set(
    ctx: RunContext[LeadDeps],
    name: str,
    record_type: str = "transcript",
    step_id: str | None = None,
    gene_ids: list[str] | None = None,
) -> ToolReturn[GeneSetCreatedResponse]:
    """Save a gene set in the user's Workbench.

    This is the save the user asks for when they say "save these genes as a
    gene set". The set appears in the Workbench sidebar, and its id is what
    enrichment, export, EDA and the control tools take. ``remember`` stores a
    note about a set; it creates none.

    Args:
        name: The name the user gave the set.
        record_type: Record type (default 'transcript').
        step_id: The step of THIS conversation's strategy whose genes to save,
            by its graph id (e.g. 'step_3'). Leave it out for the strategy's
            root step. The genes of a step are read from that step on
            VEuPathDB, and its WDK ids come from the strategy; never type one.
        gene_ids: A list of gene IDs the user pasted or this turn computed,
            which no step holds. It saves that list alone, so leave it out
            whenever the genes are a step's.
    """
    return await workbench.create_workbench_gene_set(
        inner_context(ctx),
        name=name,
        record_type=record_type,
        step_id=step_id,
        gene_ids=gene_ids,
    )


async def list_workbench_gene_sets(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[GeneSetListResponse]:
    """List the gene sets in the user's Workbench, each with its id.

    Call it before you use a gene-set id you did not just create, and when a
    tool answers that an id names nothing.
    """
    return await workbench.list_workbench_gene_sets(inner_context(ctx))


@durable_agent_tool(GENESET_ENRICHMENT)
async def run_gene_set_enrichment(
    ctx: RunContext[LeadDeps],
    gene_set_id: str,
    enrichment_types: list[EnrichmentAnalysisType] | None = None,
) -> dict[str, Any]:
    """Run enrichment analysis on a gene set in the Workbench.

    This is the enrichment the user asks for when they name a saved set. Take
    the id from ``list_workbench_gene_sets`` or from the save that created it.

    Durable: the analysis runs on the worker, the turn ends while the GO,
    pathway and word phases run, and you are called again with the summary
    (the gene set's id, ``geneCount``, ``enrichmentResults``, ``downloads``).
    Name the top terms from the ``enrichmentResults`` you are answered with.

    The set needs a WDK step id or search parameters, so the service can
    recover the background gene universe.

    Args:
        gene_set_id: ID of the gene set to run enrichment on.
        enrichment_types: Types of enrichment to run. Options: ``go_function``,
            ``go_process``, ``go_component``, ``pathway``, ``word``. Default:
            all five types.
    """
    del ctx, gene_set_id, enrichment_types
    msg = "run_gene_set_enrichment runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)


async def export_gene_set(
    ctx: RunContext[LeadDeps],
    gene_set_id: str,
    output_format: str = "csv",
) -> ToolReturn[ExportResultResponse]:
    """Export a saved gene set as a downloadable CSV or TXT file.

    This is the download the user asks for when they name a set in their
    Workbench. Take the id from ``list_workbench_gene_sets``. The reply carries
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


async def get_live_strategy_state(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[LiveStrategyState]:
    """Read the strategy as it exists RIGHT NOW, bypassing the Ledger's cache.

    The Ledger's build counts describe the last build this conversation ran.
    The user can change the strategy between turns (graph editor, VEuPathDB
    web UI), which leaves those counts wrong. Call this before stating any
    result count, parameter value, or step list as current fact - and always
    when the Ledger shows a STALE marker or the user asks what the strategy
    does "now".

    Every count comes from the site. An ``estimatedSize`` or ``rootCount`` of
    null is UNKNOWN, never zero: say the count is not available for that step
    rather than reporting a number from an earlier turn. Describe a step from
    its ``parameters``, which are the values stored on it; its name can still
    describe the value it was built with.
    """
    live = await read_live_state(
        ctx.deps.runtime.strategy_session,
        ctx.deps.runtime.site_id,
    )
    if not live.step_count:
        return with_summary(live, "No strategy yet", ctx=ctx, status="empty")
    genes = live.root_count
    if genes is None:
        return with_summary(
            live,
            f"{live.step_count} steps, count not available",
            ctx=ctx,
            status="warn",
        )
    return with_summary(
        live,
        f"{live.step_count} steps, {genes:,} genes",
        ctx=ctx,
        status="ok" if genes else "empty",
    )


async def clear_strategy(
    ctx: RunContext[LeadDeps],
    *,
    confirm: bool,
) -> ToolReturn[ClearStrategyResult]:
    """Throw the whole strategy away so the user can start over.

    This is the ONLY deliberate destructive path. Use it when the user asks to
    scrap the strategy and begin again, and never as a way around
    ``build_strategy``'s refusal on a thread that already has one: a request
    that changes what the strategy asks is ``edit_strategy``.

    Every step goes from this thread, and the next build creates a strategy of
    its own on VEuPathDB instead of reusing the one that stood here. The
    cleared state appends a revision, so a revert restores what this call
    cleared. The user approves the call before it runs, so do not also ask in
    prose. After it returns, frame and build afresh.

    ``confirm`` must be true; the call is refused otherwise.
    """
    inner = inner_context(ctx)
    cleared = await conversation.clear_strategy(inner, confirm=confirm)
    ctx.deps.state.turn_markers.edited = True
    return cleared


async def delete_step(
    ctx: RunContext[LeadDeps],
    step_id: str,
) -> ToolReturn[JSONObject]:
    """Remove one step from the strategy.

    This is how a step the user wants gone leaves: a step they say is wrong, a
    step left over from an earlier turn, or a step standing outside the
    strategy. A step under a combine takes that combine with it and its
    sibling takes their place, and a combine under a transform leaves with its
    secondary branch so the transform reads its primary. The strategy's own
    root collapses onto its primary input when it is a combine, and any other
    root leaves with whatever hangs under it. Two calls are refused: a
    transform nothing can take the place of (the strategy's root one, and one
    under another transform), and any root of more than one step on a thread
    that holds several roots and no push says which is the strategy - name a
    step under the one you mean instead. A loose step of its own goes. The
    write appends a revision, so a revert restores what it removed, and the
    user approves the call before it runs, so do not also ask in prose.

    Args:
        step_id: The step to remove, by the id the strategy graph shows.
    """
    inner = inner_context(ctx)
    deleted = await strategy_edits.delete_the_step(
        inner, step_id, surface=DeleteSurface.LEAD
    )
    ctx.deps.state.turn_markers.edited = True
    if ctx.deps.state.domain.operational_spec is not None:
        ctx.deps.state.domain.operational_spec = (
            inner.deps.agent_state.operational_spec_draft
        )
    return deleted


def read_ledger_section(
    ctx: RunContext[LeadDeps],
    section: LedgerSectionName,
) -> ToolReturn[str]:
    """Return the full detail of one Ledger section.

    The pinned summary already shows counts and derived booleans; use
    this when you need step-level detail (failed step IDs, open slot
    questions, fit-report rationales) before deciding the next move.
    """
    ledger = derive_ledger(ctx.deps.state, ctx.deps.intent)
    return with_summary(
        ledger.render_section(section),
        f"Read {section}",
        ctx=ctx,
    )
