"""Agent tools that find an EDA study and read its shape."""

from __future__ import annotations

from assistant_core.graph.tool_summary import truncate_summary, with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._eda_models import (
    EdaStudyCardOut,
    EdaStudyDescription,
    EdaStudySearchResult,
)
from pathfinder.services.eda.catalog import (
    StudySearch,
    UnknownEdaDatasetError,
    get_study_detail_for_dataset,
    search_studies,
)
from pathfinder.services.eda.description import (
    UnknownEdaEntityError,
    describe_study,
    permission_facts,
)

# A card says enough to pick the study. The whole description travels in
# describe_eda_study, on the one dataset the model picks.
_CARD_DESCRIPTION_CHARS = 240

_FILTER_GUIDANCE = (
    "Filter this study with set_eda_filters. Copy an entityId and a "
    "variableId from the lists above; a variableId is only valid on the "
    "entity that declares it. Pick the filter type from the variable's "
    "own type, not from what the value looks like. Check every string "
    "value against the variable's vocabulary yourself: an invented value "
    "returns a count of zero with no error."
)

_DESCRIPTION_GUIDANCE = (
    "Every description here is cut short. Call describe_eda_study on the "
    "datasetId you pick, before opening an analysis: it reads that study in "
    "full - its entities, its variables, and what this account may do with it."
)

_ENTITY_GUIDANCE = (
    "Call describe_eda_study again with an entity_id to read that entity's "
    "variables. A study can declare thousands, so they travel one entity at "
    "a time."
)


def _ranking_guidance(found: StudySearch) -> str:
    """What the ranking says about a study the model cannot see in it."""
    if found.ranking == "name":
        return found.guidance
    return (
        f"These are the closest studies in this site's catalog of "
        f"{found.catalog_size}. A study named by author, title or accession "
        f"that is not among them is not on this site, so offer the closest "
        f"one or ask which to use instead of searching again."
    )


def _ranking_summary(found: StudySearch, query: str) -> str:
    """The line the recorded turn carries, in the terms of the ranking."""
    if found.ranking == "name":
        return f"{len(found.cards)} studies matched {query}"
    best = max(card.relevance for card in found.cards)
    return (
        f"{len(found.cards)} closest of {found.catalog_size} studies on this "
        f"site (best match {best:.2f})"
    )


async def search_eda_studies(
    ctx: RunContext[LeadDeps],
    query: str,
    limit: int = 5,
) -> ToolReturn[EdaStudySearchResult]:
    """Find an EDA study by what it measures.

    EDA studies are the sample-level datasets behind VEuPathDB's expression,
    phenotype and antibody-array searches. Use this when the user names a
    dataset, an experiment, a condition or a comparison - "the heat shock
    RNA-Seq data", "rodent malaria phenotypes", "febrile against normal" -
    rather than a gene attribute.

    Each result carries a ``datasetId`` (a ``DS_`` or ``EDAUD_`` id) and a
    ``studyId``. Every later EDA tool takes the ``datasetId``; never build one
    from the other. ``canSubset`` false means this account cannot count that
    study, and ``canExportRows`` false means it cannot export its rows into a
    step, so say so instead of trying.

    Args:
        ctx: Agent run context.
        query: What the study should measure, in the user's own words.
        limit: Maximum studies to return.
    """
    found = await search_studies(ctx.deps.runtime.site_id, query, limit=limit)
    if not found.cards:
        return with_summary(
            EdaStudySearchResult(
                guidance=(
                    f"No EDA study on this site matches {query!r}. EDA covers "
                    f"sample-level expression, phenotype and antibody-array "
                    f"datasets only. If the question is about gene attributes, "
                    f"use search_for_searches instead."
                ),
            ),
            f"No study matched {query}",
            ctx=ctx,
            status="empty",
        )
    result = EdaStudySearchResult(
        studies=[
            EdaStudyCardOut(
                dataset_id=card.dataset_id,
                study_id=card.study_id,
                display_name=card.display_name,
                short_display_name=card.short_display_name,
                description=truncate_summary(
                    card.description,
                    limit=_CARD_DESCRIPTION_CHARS,
                ),
                source_type=card.source_type,
                relevance=card.relevance,
                can_subset=card.can_subset,
                can_export_rows=card.can_export_rows,
            )
            for card in found.cards
        ],
        guidance=f"{_ranking_guidance(found)} {_DESCRIPTION_GUIDANCE}",
    )
    return with_summary(result, _ranking_summary(found, query), ctx=ctx)


async def describe_eda_study(
    ctx: RunContext[LeadDeps],
    dataset_id: str,
    entity_id: str | None = None,
) -> ToolReturn[EdaStudyDescription]:
    """Read an EDA study's entity tree, and one entity's filterable variables.

    Call it first with no ``entity_id`` to get the entity tree: each entity is
    one table of records, a child entity holds several rows per parent row,
    and the counts a subset produces are per entity. Then call it again with
    the ``entity_id`` you want, to get that entity's variables. A study can
    declare thousands of variables, so they never travel all at once.

    Each variable carries the exact ``filterType`` it takes, its vocabulary or
    its declared bounds, and whether one record holds several values. A
    ``geneEntityProblem`` means the study cannot export a gene list into a
    strategy step; the analysis is still worth reading.

    Args:
        ctx: Agent run context.
        dataset_id: The dataset id from search_eda_studies.
        entity_id: The entity whose variables to read.
    """
    try:
        entry, study = await get_study_detail_for_dataset(
            ctx.deps.runtime.site_id, dataset_id
        )
    except UnknownEdaDatasetError as exc:
        msg = f"{exc.guidance} Call search_eda_studies to find a real dataset id."
        raise ModelRetry(msg) from exc
    try:
        described = describe_study(
            permission_facts(entry),
            study,
            dataset_id=dataset_id,
            entity_id=entity_id,
        )
    except UnknownEdaEntityError as exc:
        raise ModelRetry(exc.guidance) from exc
    # A study can declare thousands of variables, so they travel one entity
    # at a time and the tree call carries none of them.
    variables = [] if entity_id is None else described.variables
    description = EdaStudyDescription(
        **described.model_dump(exclude={"variables"}),
        variables=variables,
        guidance=_FILTER_GUIDANCE if entity_id is not None else _ENTITY_GUIDANCE,
    )
    shape = (
        f"{description.display_name}: {len(description.entities)} entities, "
        f"{len(variables)} variables"
    )
    if description.gene_entity_id is None:
        return with_summary(
            description,
            f"{shape}, no gene id variable",
            ctx=ctx,
            status="warn",
        )
    return with_summary(description, shape, ctx=ctx)
