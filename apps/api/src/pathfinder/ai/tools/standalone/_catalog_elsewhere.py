"""Other sites' experiments beside the own-site searches: shown, read, never bound."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import WDKTreeBoxVocabNode
from veupathdb.wdk import WDKSearch
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ExperimentMatch, UnknownExperimentError
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from pathfinder.ai.graph.runtime import AgentDeps

logger = get_logger(__name__)

# The gene record type, and the parameter a gene search names its organism in.
_GENES = "transcript"
_ORGANISM = "organism"
# A card lists this many of the searches it feeds on its own site.
_SEARCHES_SHOWN = 6


class _OtherSiteExperiment(CamelModel):
    site: str
    dataset_id: str
    similarity: float
    line: str


class _OtherSites(CamelModel):
    note: str
    experiments: list[_OtherSiteExperiment]


def with_other_sites(
    own: list[JSONObject],
    elsewhere: Sequence[ExperimentMatch],
    shown: Collection[str],
    site_id: str,
) -> list[JSONObject]:
    """The own-site answer unchanged, and the unseen other-site entries after it."""
    seen = set(shown)
    unseen: list[_OtherSiteExperiment] = []
    for match in elsewhere:
        card = match.card
        if card.dataset_id in seen:
            continue
        seen.add(card.dataset_id)
        unseen.append(
            _OtherSiteExperiment(
                site=card.site_id,
                dataset_id=card.dataset_id,
                similarity=round(match.similarity, 2),
                line=card.line(),
            )
        )
    if not unseen:
        return own
    block = _OtherSites(
        note=(
            f"Experiments on other VEuPathDB sites. None can be bound on {site_id}. "
            f"Read one with read_experiment to name a condition, a stage or an "
            f"organism in a search on {site_id}."
        ),
        experiments=unseen,
    )
    return [*own, {"otherSites": block.model_dump(by_alias=True)}]


async def rank_other_sites(
    ctx: RunContext[AgentDeps], query: str
) -> list[ExperimentMatch]:
    """Other sites' experiments closest to the query, none when the index is down."""
    try:
        return await catalog.rank_experiments_elsewhere(ctx.deps.site_id, query)
    except SemanticIndexUnavailableError as exc:
        logger.warning("Other sites' experiments were not ranked", error=str(exc))
        return []


async def own_search_names(site_id: str) -> frozenset[str]:
    """The gene searches the thread's own site publishes."""
    return frozenset(
        listed.url_segment for listed in await catalog.get_raw_searches(site_id, _GENES)
    )


def another_sites_entry(ctx: RunContext[AgentDeps], value: str) -> str | None:
    """Why a value another site's experiment named cannot be bound here."""
    shown = ctx.deps.agent_state.elsewhere
    entry = shown.get(value) or next(
        (s for s in shown.values() if value in s.searches_only_there), None
    )
    if entry is None:
        return None
    what = "a dataset" if value == entry.dataset_id else "a search"
    site_id = ctx.deps.site_id
    return (
        f"{value} is {what} on {entry.site_id}, and this strategy runs on {site_id}. "
        f"An experiment on another site informs a criterion and is never bound: take "
        f"its condition or stage into search_for_searches on {site_id}, cite it in "
        f"why.sources, or carry its genes by orthology on the VEuPathDB portal, where "
        f"one strategy holds both organisms. Nothing was recorded."
    )


def tree_tops(definition: WDKSearch, param_name: str) -> list[str]:
    """The top entries of a parameter's vocabulary tree, in the sheet's order.

    WDK roots a tree at a node that is not an entry, so its children are the top.
    A flat vocabulary has no tree and answers none.
    """
    param = next((p for p in definition.parameters or [] if p.name == param_name), None)
    match None if param is None else param.vocabulary:
        case WDKTreeBoxVocabNode() as root:
            return [child.data.display for child in root.children]
        case _:
            return []


def joined(names: Sequence[str]) -> str:
    """The names as a sentence lists them: "A", "A and B", "A, B and C"."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def reach_sentence(
    definition: WDKSearch, param_name: str, site_id: str, organism: str
) -> str:
    """What the transform's organism tree reaches, and where a transform to the
    organism runs instead."""
    return (
        f"{definition.display_name} on {site_id} reaches "
        f"{joined(tree_tops(definition, param_name))}; a transform to "
        f"{organism} runs on the VEuPathDB portal, where one strategy holds both "
        f"organisms."
    )


async def _orthology_route(site_id: str, organism: str) -> str:
    """The sentence for the site's gene transform that names an organism."""
    for listed in await catalog.get_raw_searches(site_id, _GENES):
        inputs = listed.allowed_primary_input_record_class_names or []
        if _GENES in inputs and _ORGANISM in listed.param_names:
            definition = await catalog.read_search_definition(
                site_id, _GENES, listed.url_segment
            )
            return reach_sentence(definition, _ORGANISM, site_id, organism)
    return (
        f"No transform on {site_id} names an organism; the VEuPathDB portal holds "
        f"{organism} and this site's organisms in one strategy."
    )


class ExperimentRead(CamelModel):
    """Another site's experiment, what it feeds there, and how its genes reach here."""

    site: str
    dataset_id: str
    name: str
    organism: str
    assay: str
    attribution: str
    summary: str
    pmids: list[str]
    record_url: str
    searches: list[str]
    where_they_run: str
    orthology: str


async def read_experiment(
    ctx: RunContext[AgentDeps], dataset_id: str
) -> ToolReturn[ExperimentRead]:
    """Read one experiment another VEuPathDB site holds.

    search_for_searches shows other sites' experiments in its otherSites entry.
    The card names the condition, the stage, the organism and the publications,
    which may name a search on this site. Its record URL and PMIDs may be cited
    in why.sources. Its searches run on its own site and are never bound here.

    Args:
        ctx: Agent run context.
        dataset_id: The dataset id of one experiment in the otherSites entry of
            search_for_searches.
    """
    elsewhere = ctx.deps.agent_state.elsewhere
    site_id = ctx.deps.site_id
    shown = elsewhere.get(dataset_id)
    if shown is None:
        where = (
            f"Read one of: {', '.join(elsewhere)}."
            if elsewhere
            else "search_for_searches shows other sites' experiments in its "
            "otherSites entry."
        )
        msg = f"{dataset_id} is not an experiment this pass showed. {where}"
        raise ModelRetry(msg)
    try:
        card = await catalog.read_experiment(shown.site_id, dataset_id)
    except UnknownExperimentError as exc:
        msg = (
            f"{exc.site_id} no longer holds {exc.dataset_id}, so it cannot be read. "
            f"Go on with the searches on {site_id}."
        )
        raise ModelRetry(msg) from exc
    except SemanticIndexUnavailableError as exc:
        msg = (
            f"The experiment store does not answer now, so {dataset_id} cannot be "
            f"read. Go on with the searches on {site_id}."
        )
        raise ModelRetry(msg) from exc
    markers = ctx.deps.turn_markers
    for reference in (card.record_url, *card.pmids):
        markers.record_retrieved_source(reference)
    read = ExperimentRead(
        site=card.site_id,
        dataset_id=card.dataset_id,
        name=card.name,
        organism=card.organism,
        assay=card.assay,
        attribution=card.attribution,
        summary=card.summary,
        pmids=card.pmids,
        record_url=card.record_url,
        searches=card.searches[:_SEARCHES_SHOWN],
        where_they_run=f"These searches run on {card.site_id}, not on {site_id}.",
        orthology=await _orthology_route(site_id, card.organism),
    )
    return with_summary(read, card.line(), ctx=ctx)
