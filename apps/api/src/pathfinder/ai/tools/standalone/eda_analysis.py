"""Agent tools that open an EDA analysis, subset it, and count what is left."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.domain import find_gene_entity

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._eda_guidance import (
    APPLIED_GUIDANCE,
    SHEET_GUIDANCE,
    entity_count_clause,
    opened_guidance,
    preview_guidance,
)
from pathfinder.ai.tools.standalone._eda_models import (
    EdaAnalysisOpened,
    EdaFiltersResult,
    EdaSubsetPreviewResult,
)
from pathfinder.ai.tools.standalone._eda_sheet import open_sheet
from pathfinder.ai.tools.standalone.eda_stream_parts import (
    analysis_state_chunks_if_changed,
    eda_subset_preview_chunk,
)
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.services.eda import EdaFilter, EdaStudyDetail
from pathfinder.services.eda.authoring import SubsetRejectedError, preview_subset
from pathfinder.services.eda.binding import (
    ConversationAnalysisView,
    apply_filters,
    bind_analysis,
    bound_conversation_analysis,
    read_analysis,
    record_subset_preview,
)
from pathfinder.services.eda.catalog import (
    UnknownEdaDatasetError,
    get_study_detail_for_dataset,
)
from pathfinder.services.eda.description import (
    EdaPermissionFacts,
    permission_facts,
    variable_at,
)


async def _study(
    site_id: str,
    dataset_id: str,
) -> tuple[EdaPermissionFacts, EdaStudyDetail]:
    """The study behind a dataset id, or the retry that names the right tool."""
    try:
        entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    except UnknownEdaDatasetError as exc:
        msg = f"{exc.guidance} Call search_eda_studies to find a real dataset id."
        raise ModelRetry(msg) from exc
    return permission_facts(entry), study


async def open_eda_analysis(
    ctx: RunContext[LeadDeps],
    dataset_id: str,
    purpose: str,
) -> ToolReturn[EdaAnalysisOpened]:
    """Open an EDA analysis on a study, so filters and computes have somewhere
    to live.

    This creates a real analysis document in the researcher's VEuPathDB
    workspace and binds it to this conversation. From then on set_eda_filters,
    preview_eda_subset, run_eda_compute and create_eda_step all act on it, and
    the researcher sees the same analysis in the EDA tab and on the VEuPathDB
    site.

    One conversation holds one open analysis at a time. Opening a second one
    replaces the binding, so open the study you actually mean, after
    describe_eda_study confirms it carries the variables the question needs.

    ``purpose`` becomes the analysis's display name in the researcher's
    workspace, so write what the subset is for in their words - "P. berghei
    rows with successful genetic modification", not "analysis 1". The
    workspace label holds 50 characters, and a longer one is cut to fit.

    Args:
        ctx: Agent run context.
        dataset_id: The dataset id from search_eda_studies. A ``DS_`` or
            ``EDAUD_`` id, never a ``STUDY_`` id.
        purpose: What this analysis is for, in the researcher's words.
    """
    site_id = ctx.deps.runtime.site_id
    _entry, study = await _study(site_id, dataset_id)
    gene = find_gene_entity(study, subject="strategy step")
    state = await bind_analysis(
        site_id,
        dataset_id=dataset_id,
        conversation_id=ctx.deps.state.conversation_id,
        display_name=purpose,
    )
    ctx.deps.state.domain.close_eda_sheet_of_another_study(dataset_id)
    # Nothing is counted on an analysis this call has just created.
    ctx.deps.state.domain.open_eda_analysis = OpenEdaAnalysis(
        dataset_id=dataset_id,
        analysis_id=state.analysis_id,
    )
    opened = EdaAnalysisOpened(
        analysis_id=state.analysis_id,
        dataset_id=dataset_id,
        study_id=state.study_id,
        display_name=state.display_name,
        study_display_name=state.study_display_name,
        gene_entity_id=gene.entity_id,
        can_export_rows=state.can_export_rows,
        guidance=opened_guidance(
            gene_problem=gene.error, can_export=state.can_export_rows
        ),
    )
    return with_summary(
        opened,
        f"Opened {state.display_name}",
        ctx=ctx,
        extra=analysis_state_chunks_if_changed(state, domain=ctx.deps.state.domain),
    )


async def bound_analysis(
    ctx: RunContext[LeadDeps],
) -> ConversationAnalysisView | None:
    """The analysis this conversation has open, or None when it has none."""
    return await bound_conversation_analysis(
        conversation_id=ctx.deps.state.conversation_id
    )


async def set_eda_filters(
    ctx: RunContext[LeadDeps],
    *,
    dataset_id: str,
    filters: list[EdaFilter] | None = None,
) -> ToolReturn[EdaFiltersResult]:
    """Set the whole subset of the open EDA analysis, in two calls.

    Call this ONCE with no ``filters`` to open the FILTER SHEET: every
    filterable variable of the study with its entity, its exact filter type,
    its vocabulary or its range, and one complete example filter object you can
    copy. The sheet is pinned under "Open EDA filter sheet" in your
    instructions and stays there until the subset is applied or the study is
    closed; nothing is recorded by that call.

    Then call it AGAIN with ``filters`` set to the whole array you want. The
    array REPLACES the analysis's subset; it is not a patch, so send every
    filter that should apply. An empty array clears the subset and means the
    whole study.

    Writing the array, and every rule here is one the service will not enforce:

    - Copy ``entityId`` and ``variableId`` together from one sheet entry. A
      variableId is only valid on the entity that declares it.
    - Take ``type`` from the entry's ``filterType``, never from what the value
      looks like. A longitude variable is not a number variable, and a category
      variable holds no values at all.
    - For a string variable, every value must appear in the entry's
      ``vocabulary``. An invented value returns a count of zero with no error,
      so it looks like a real empty result.
    - For a date variable, append ``T00:00:00`` to every bound. The sheet
      already shows the bounds in that form. A bare ``2017-05-05`` is a server
      error.
    - The array is AND, always, across variables and across entities. To say
      "berghei OR falciparum", write ONE stringSet holding both. Two entries on
      one single-valued variable select nothing.
    - ``isMultiValued`` true means one record holds several values, so the
      per-value counts do not add up to the record count and two filters on
      that variable mean "has both".
    - A multiFilter targets a category whose ``filterType`` is ``multiFilter``
      and names its ``subFilterVariableIds``; its ``operation`` is ``union``
      for OR or ``intersect`` for AND. It is the only OR in the algebra.
    - Never put a range's ``min`` above its ``max``, and never set a
      longitudeRange's ``left`` equal to its ``right``. Both are accepted and
      both mean something other than what they look like.

    A rejected array comes back as a retry naming the offending value and the
    valid ones. Fix that value and re-send the whole array; do not ask for the
    sheet again.

    Args:
        ctx: Agent run context.
        dataset_id: The dataset of the open analysis.
        filters: The complete filter array, or omit it to read the sheet.
    """
    site_id = ctx.deps.runtime.site_id
    bound = await _bound_or_retry(ctx, dataset_id)
    if filters is None:
        _entry, study = await _study(site_id, dataset_id)
        variables = open_sheet(ctx.deps.state.domain, study, dataset_id)
        return with_summary(
            EdaFiltersResult(
                analysis_id=bound.analysis_id,
                dataset_id=dataset_id,
                sheet_pinned=True,
                guidance=SHEET_GUIDANCE,
            ),
            f"sheet pinned, {variables} filters to choose from",
            ctx=ctx,
            status="warn",
        )
    try:
        state = await apply_filters(
            site_id,
            conversation_id=ctx.deps.state.conversation_id,
            analysis_id=bound.analysis_id,
            dataset_id=dataset_id,
            filters=filters,
        )
    except SubsetRejectedError as exc:
        msg = (
            f"{' '.join(exc.messages)} The valid values are listed above; do not "
            f"request the sheet again."
        )
        raise ModelRetry(msg) from exc
    ctx.deps.state.domain.close_eda_sheet()
    ctx.deps.state.domain.open_eda_analysis = OpenEdaAnalysis(
        dataset_id=dataset_id,
        analysis_id=bound.analysis_id,
    )
    return with_summary(
        EdaFiltersResult(
            applied=True,
            analysis_id=bound.analysis_id,
            dataset_id=dataset_id,
            num_filters=state.num_filters,
            filter_summaries=state.filter_summaries,
            guidance=APPLIED_GUIDANCE,
        ),
        f"{state.num_filters} filters: {'; '.join(state.filter_summaries)}",
        ctx=ctx,
        extra=analysis_state_chunks_if_changed(state, domain=ctx.deps.state.domain),
    )


async def _bound_or_retry(
    ctx: RunContext[LeadDeps],
    dataset_id: str,
) -> ConversationAnalysisView:
    """The open analysis, or the retry that tells the model to open one."""
    bound = await bound_analysis(ctx)
    if bound is None:
        msg = (
            f"This conversation has no study open. Call open_eda_analysis on "
            f"dataset {dataset_id!r} first."
        )
        raise ModelRetry(msg)
    if bound.dataset_id != dataset_id:
        msg = (
            f"The open analysis is {bound.analysis_id} on dataset "
            f"{bound.dataset_id!r}, and this call names {dataset_id!r}. Act on "
            f"the open analysis, or call open_eda_analysis to change it."
        )
        raise ModelRetry(msg)
    return bound


async def preview_eda_subset(
    ctx: RunContext[LeadDeps],
    *,
    entity_id: str,
    distribution_variable_id: str | None = None,
    caption: str = "",
) -> ToolReturn[EdaSubsetPreviewResult]:
    """Count what the open analysis's filters select, on one entity.

    Call this after every set_eda_filters, before you tell the researcher a
    number and before you create a step. It returns the filtered count and the
    unfiltered count for that entity, so the effect of the subset is visible.

    ``entity_id`` decides WHAT is counted, and it is independent of which
    entities the filters name: a filter on a child entity restricts the parent
    to parents that still have a surviving child, and a filter on a parent
    restricts the child to children under a surviving parent.

    Name ``distribution_variable_id`` to also get that variable's histogram
    under the subset. That is what shows the researcher the shape of what is
    left.

    A count of zero is a real answer, not an error. Say which filter emptied
    the subset and offer one concrete way to widen it.

    Write ``caption`` whenever you ask for a histogram. It is the one sentence
    printed under the plot, so it says what the plot SHOWS in the
    researcher's terms - "Distribution of per-gene sense counts across the 12
    febrile and normal samples" - never an internal name and never a repeat of
    the numbers, which the figure already carries.

    Args:
        ctx: Agent run context.
        entity_id: The entity whose records are counted.
        distribution_variable_id: A variable on that entity to histogram.
        caption: One sentence describing what the distribution shows.
    """
    site_id = ctx.deps.runtime.site_id
    bound = await bound_analysis(ctx)
    if bound is None:
        msg = (
            "This conversation has no study open, so there is no subset to "
            "count. Call open_eda_analysis first."
        )
        raise ModelRetry(msg)
    analysis = await read_analysis(site_id, analysis_id=bound.analysis_id)
    filters = analysis.descriptor.subset.descriptor
    preview = await preview_subset(
        site_id,
        dataset_id=bound.dataset_id,
        entity_id=entity_id,
        filters=filters,
        distribution_variable_id=distribution_variable_id,
    )
    await record_subset_preview(conversation_id=ctx.deps.state.conversation_id)
    ctx.deps.state.domain.open_eda_analysis = OpenEdaAnalysis(
        dataset_id=bound.dataset_id,
        analysis_id=bound.analysis_id,
        subset_previewed=True,
    )
    _entry, study = await _study(site_id, bound.dataset_id)
    variable = variable_at(study, entity_id, distribution_variable_id)
    statistics = (
        None if preview.distribution is None else preview.distribution.statistics
    )
    result = EdaSubsetPreviewResult(
        entity_id=preview.entity_id,
        entity_display_name=preview.entity_display_name,
        count=preview.count,
        unfiltered_count=preview.unfiltered_count,
        variable_id=distribution_variable_id,
        variable_display_name="" if variable is None else variable.display_name,
        is_multi_valued=variable is not None and variable.is_multi_valued,
        labels=[]
        if preview.distribution is None
        else [bin_.bin_label for bin_ in preview.distribution.histogram],
        values=[]
        if preview.distribution is None
        else [bin_.value for bin_ in preview.distribution.histogram],
        num_var_values=0 if statistics is None else statistics.num_var_values,
        num_missing_cases=0 if statistics is None else statistics.num_missing_cases,
        distribution_note=preview.distribution_note,
        guidance=preview_guidance(
            preview_count=preview.count,
            unfiltered_count=preview.unfiltered_count,
            entity_display_name=preview.entity_display_name,
            has_filters=bool(filters),
            is_multi_valued=variable is not None and variable.is_multi_valued,
            num_missing_cases=0 if statistics is None else statistics.num_missing_cases,
        ),
    )
    chunk = eda_subset_preview_chunk(
        dataset_id=bound.dataset_id,
        analysis_id=bound.analysis_id,
        preview=preview,
        variable_id=distribution_variable_id,
        variable_display_name=result.variable_display_name,
        is_multi_valued=result.is_multi_valued,
        caption=caption,
    )
    return with_summary(
        result,
        entity_count_clause(preview),
        ctx=ctx,
        status="ok" if preview.count else "empty",
        extra=[chunk],
    )
