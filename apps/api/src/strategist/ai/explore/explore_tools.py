from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Annotated

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import Field, JsonValue, TypeAdapter
from pydantic_ai import ModelRetry, RunContext, Tool
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp.catalog import GetParameterOptionsResult, SearchOverviewResult

from strategist.ai.lead.dispatch_context import inner_context
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone import (
    _catalog_elsewhere,
    catalog,
    catalog_discovery,
)
from strategist.ai.tools.standalone._catalog_elsewhere import ExperimentRead
from strategist.ai.tools.standalone.record_reads import record_columns_block
from strategist.ai.tools.standalone.search_reads import resolved_search
from strategist.domain.comparison_facts import ComparedVariant, ComparisonFact
from strategist.domain.refusal import Check, Problems, RefusalKey
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.strategy.ranking import score_rows
from strategist.domain.strategy.reading_plan import OfferedReading
from strategist.platform.refusals import problems_of_retry, refuse_problems
from strategist.services.evidence.comparisons import (
    run_reading_count,
    run_reading_spec,
)
from strategist.services.experiment.reading_count import (
    ProposedReading,
    ProposedReadingDraft,
    drafted,
)
from strategist.services.experiment.variant_comparison import VariantSpec

_GENES = "transcript"


class ProposedCount(CamelModel):
    label: str
    plan: str
    gene_count: int | None
    not_counted: str = ""
    also: str = ""
    scores: dict[int, int] = Field(default_factory=dict)


@dataclass(frozen=True)
class CheckedProposal:
    proposal: ProposedReading
    searches: list[VariantSpec]
    spec: OperationalSpec


async def _resolved(
    ctx: RunContext[LeadDeps], draft: ProposedReadingDraft
) -> tuple[list[VariantSpec], Problems]:
    found = Problems()
    searches: list[VariantSpec] = []
    for search in draft.searches:
        key = RefusalKey(
            check=Check.PROPOSAL_SEARCH, criterion=draft.title, search=search.label
        )
        try:
            searches.append(await resolved_search(ctx, search, record_type=_GENES))
        except ModelRetry as refused:
            found = found.plus(problems_of_retry(refused, key))
    return searches, found


def _repeated(check: Check, named: list[str], what: str, fix: str) -> Problems:
    if len(set(named)) == len(named):
        return Problems()
    return Problems.one(
        RefusalKey(check=check), f"Two proposals {what}: {named}. {fix}"
    )


async def checked_proposals(
    ctx: RunContext[LeadDeps], drafts: list[ProposedReadingDraft]
) -> list[CheckedProposal]:
    found = Problems()
    checked: list[CheckedProposal] = []
    for draft in drafts:
        searches, refused = await _resolved(ctx, draft)
        match drafted(draft):
            case Problems() as shape:
                found = found.plus(shape).plus(refused)
            case proposal if refused.empty:
                spec = await run_reading_spec(ctx.deps.site_id, proposal, searches)
                checked.append(CheckedProposal(proposal, searches, spec))
            case _:
                found = found.plus(refused)
    found = found.plus(
        _repeated(
            Check.PROPOSAL_TITLE,
            [draft.title for draft in drafts],
            "carry the same title",
            "Give each plan its own.",
        )
    ).plus(
        _repeated(
            Check.PROPOSAL_PLAN,
            [held.spec.goal for held in checked],
            "state the same plan",
            "Propose each plan once.",
        )
    )
    refuse_problems(found)
    return checked


async def _offered(
    ctx: RunContext[LeadDeps], checked: CheckedProposal
) -> OfferedReading:
    proposal = checked.proposal
    counted = await run_reading_count(
        ctx.deps.site_id, proposal, checked.searches, checked.spec
    )
    return OfferedReading(
        label=proposal.title,
        plan=counted.label,
        gene_count=counted.gene_count,
        spec=counted.spec,
        not_counted=counted.not_counted,
        also=proposal.also,
        scores=counted.scores,
    )


def _fact(offered: OfferedReading, gene_count: int) -> ComparisonFact:
    counted = ComparedVariant(label=offered.label, gene_count=gene_count)
    top = sum(c.weight for c in offered.spec.criteria if c.weight is not None)
    scored = score_rows(offered.scores, top=top, title=offered.label)
    return ComparisonFact(variants=[counted, *scored], on_its_card=False)


async def propose_readings(
    ctx: RunContext[LeadDeps],
    readings: Annotated[list[ProposedReadingDraft], Field(min_length=1)],
) -> ToolReturn[list[ProposedCount]]:
    """Propose plans Build can build, each counted when it can be. Read-only.

    A proposal is the catalog searches of one plan and how they combine, so a
    request of two criteria is one proposal of two searches. Give each a short
    title; Strategist writes its plan from its searches, values and operators
    and shows it under the title. A
    plan of searches joined by INTERSECT, UNION or MINUS is counted from each
    search's gene ids, and no step is added. A ranking plan gives each search
    a weight, 1 each unless the researcher says one kind of evidence matters
    more. It keeps every gene any search finds, scores each gene by the
    weights of the searches that find it, and is counted by score. A plan it
    cannot count is proposed as not counted yet. A later call replaces this turn's proposals,
    so propose alternatives together. Offer two or more proposals on one
    ``consult_user`` card, each option labelled exactly as returned here. One
    proposal takes no card.

    Args:
        readings: One proposal at least, each one plan.
    """
    offered = [
        await _offered(ctx, held) for held in await checked_proposals(ctx, readings)
    ]
    labels = [reading.label for reading in offered]
    state = ctx.deps.state
    state.turn_markers.proposed_readings = labels
    for reading in offered:
        state.domain.offer_reading(reading)
        if reading.gene_count is not None:
            state.turn_markers.record_comparison(_fact(reading, reading.gene_count))
    proposed = [
        ProposedCount(
            label=reading.label,
            plan=reading.plan,
            gene_count=reading.gene_count,
            not_counted=reading.not_counted,
            also=reading.also,
            scores=reading.scores,
        )
        for reading in offered
    ]
    return with_summary(
        proposed, f"{count_noun(len(proposed), 'reading')} proposed", ctx=ctx
    )


async def search_for_searches(
    ctx: RunContext[LeadDeps],
    query: str,
    record_type: str,
    keywords: list[str] | None = None,
    category: str | None = None,
    limit: int = 20,
) -> ToolReturn[list[JSONObject]]:
    """Find the site's searches nearest a question, ranked. Read-only.

    Each result gives name, displayName, description, category and the record
    type it returns. ``relevance`` is relative to the best hit, so the top hit
    reads 1.0 however weak it is. ``semanticSimilarity`` is the cosine of the
    query against the search: read it to tell a match from the best of
    nothing. ``decisionProbability``, when present, is the probability a
    Decisions choice gave that search, and a high one names the search that
    states the question. When no search states the question closely, when
    nothing matched, or when the ranking is by keyword only, the first entry is
    a note that says which. A ``recordColumns`` entry lists the record columns
    nearest the question. An ``otherSites`` entry, when present, is last: the
    experiments other VEuPathDB sites hold, each labelled with its site.
    read_experiment reads one of them.

    Args:
        query: The question in descriptive words, such as 'gametocyte RNA-Seq
            differential expression'.
        record_type: The record type whose searches are ranked, one that
            get_record_types names for this site.
        keywords: Exact identifiers to match against search names, such as a
            dataset name fragment or an organism code.
        category: One search subcategory of the site ontology.
        limit: The most results to return.
    """
    inner = inner_context(ctx)
    found = await catalog.search_for_searches(
        inner, query, record_type, keywords, category, limit
    )
    ctx.deps.shown_experiments.update(inner.deps.agent_state.elsewhere)
    block = await record_columns_block(ctx.deps.site_id, query)
    if block is None:
        return found
    rows = TypeAdapter(list[JSONObject]).validate_python(found.return_value)
    return replace(found, return_value=[*rows, block])


async def get_search_overview(
    ctx: RunContext[LeadDeps],
    search_name: str,
    record_type: str | None = None,
) -> ToolReturn[SearchOverviewResult]:
    """Read one search: its description, its required and optional parameters,
    and which parameters depend on others. Read-only.

    Args:
        search_name: The search name (urlSegment), such as 'GenesByText'.
        record_type: The search's record type. Omit it: the site names it.
    """
    return await catalog_discovery.get_search_overview(
        inner_context(ctx), search_name, record_type
    )


async def get_parameter_options(
    ctx: RunContext[LeadDeps],
    search_name: str,
    parameter_id: str,
    record_type: str | None = None,
    context_values: dict[str, JsonValue] | None = None,
    query: str | list[str] | None = None,
) -> ToolReturn[GetParameterOptionsResult]:
    """Read the values one parameter of a search allows. Read-only.

    The answer is ``parameter_info`` with the vocabulary, or
    ``parameter_not_on_search`` with the parameter names the search holds, or
    ``parent_context_required`` with the parents whose values the vocabulary
    needs. A dependent parameter's vocabulary follows its parents' values.

    Args:
        search_name: The search name (urlSegment).
        parameter_id: One parameter name get_search_overview gives for this
            search, copied exactly.
        record_type: The search's record type. Omit it: the site names it.
        context_values: The values of the parents this parameter depends on,
            each in the shape its ``statedSchema`` gives, such as
            ``{"profileset_generic": "<term>"}``.
        query: One phrase, or a list of the names of one concept, that narrows
            the vocabulary, such as ["RNA binding", "RNA recognition", "KH"].
            Hyphen and space match alike, and a phrase also matches its words
            in any order. On a filter parameter, it also reads the range of up
            to three range facets it names.
    """
    return await catalog_discovery.get_parameter_options(
        inner_context(ctx),
        search_name,
        parameter_id,
        record_type,
        context_values,
        query,
    )


async def get_record_types(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[list[dict[str, str]]]:
    """List the record types this site holds. search_for_searches ranks the
    searches of one of them. Read-only."""
    return await catalog.get_record_types(inner_context(ctx))


async def read_experiment(
    ctx: RunContext[LeadDeps], dataset_id: str
) -> ToolReturn[ExperimentRead]:
    """Read one experiment another VEuPathDB site holds. Read-only.

    The answer names the condition, the stage, the organism and the
    publications, and how its genes reach this site by orthology. Its searches
    run on its own site only. Its record URL and PMIDs are sources a reply may
    cite.

    Args:
        dataset_id: The dataset id of one experiment in the otherSites entry
            of a search_for_searches answer of this turn.
    """
    inner = inner_context(ctx)
    inner.deps.agent_state.elsewhere.update(ctx.deps.shown_experiments)
    return await _catalog_elsewhere.read_experiment(inner, dataset_id)


def catalog_reads() -> list[Tool[LeadDeps]]:
    return [
        Tool(search_for_searches),
        Tool(get_search_overview),
        Tool(get_parameter_options),
        Tool(get_record_types),
        Tool(read_experiment),
    ]
