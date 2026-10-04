"""The statistics the EDA service computes on the open analysis: the durable
dimensionality reduction and the synchronous pass-through statistics."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from assistant_core.graph.tool_summary import summary_chunks, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome
from pydantic import ConfigDict
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk
from veupathdb.eda import EdaVariableSpec

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.eda_analysis import bound_analysis
from pathfinder.ai.tools.standalone.eda_compute import EdaVariableSpecIn
from pathfinder.ai.tools.standalone.eda_stream_parts import eda_statistics_chunk
from pathfinder.domain.statistic_facts import StatisticFact, statistics_fact
from pathfinder.platform.durable_worker import durable_agent_tool
from pathfinder.services.eda.binding import read_analysis
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.statistics import (
    StatisticsRefusedError,
    StatisticsRequest,
    read_statistics_part,
)

_ESTIMATED_SECONDS = 120

STATISTIC_GUIDANCE = (
    "State each number with [stat:<id>.<row name>], using the id and the row "
    "names of the statistic above. Say a row that holds no number in your own "
    "words. Name the test the service ran; the card shows the table and every "
    "value."
)


class EdaStatisticResult(CamelModel):
    """A statistic the service computed, as the reply references it."""

    model_config = ConfigDict(extra="ignore")

    statistic: StatisticFact
    guidance: str = STATISTIC_GUIDANCE


def pca_statistic(result: Any) -> StatisticFact:
    """The reduction a finished job reports, as the turn's facts hold it."""
    return EdaStatisticResult.model_validate(result).statistic


def _pca_chunks_from_result(
    resumed: Any,
    task_id: UUID,
    tool_call_id: str | None,
) -> list[BaseChunk]:
    del task_id
    outcome = DurableOutcome.model_validate(resumed)
    if not outcome.succeeded:
        return []
    fact = pca_statistic(outcome.result)
    return summary_chunks(
        tool_call_id,
        f"{fact.value('samples')}, {fact.value('groups')}; PC1 explains "
        f"{fact.value('PC1')} of the variance and PC2 {fact.value('PC2')}",
    )


EDA_PCA = declare_durable_tool(
    tool_name="run_eda_dimensionality_reduction",
    estimated_duration_seconds=_ESTIMATED_SECONDS,
    chunks_from_result=_pca_chunks_from_result,
)


@durable_agent_tool(EDA_PCA)
async def run_eda_dimensionality_reduction(
    ctx: RunContext[LeadDeps],
    *,
    identifier_variable: EdaVariableSpecIn,
    value_variable: EdaVariableSpecIn,
    data_format: Literal["rawCounts", "normalizedValues"] = "normalizedValues",
    color_by_variable: EdaVariableSpecIn | None = None,
    caption: str = "",
) -> dict[str, Any]:
    """Run a principal component analysis of the open analysis's samples.

    The site's compute service places every sample on its principal
    components from the expression of all its genes. It runs in the
    background: the turn ends, the researcher sees progress, and you are
    called again with the result. Use it when the researcher asks whether
    conditions separate, wants an overview or a quality check of the samples,
    or before a comparison is trusted.

    - ``identifier_variable`` is the gene column, the reserved variable
      ``VEUPATHDB_GENE_ID``.
    - ``value_variable`` is the measurement column on the SAME entity, one of
      the reserved expression ids describe_eda_study lists.
    - ``data_format`` is ``rawCounts`` for read counts and
      ``normalizedValues`` for normalized expression.
    - ``color_by_variable`` is a sample variable on an ANCESTOR entity of the
      expression data. Each of its values is one colored group.

    The result names the two components with the variance each explains, the
    samples and the groups, under a statistic id. State each with
    ``[stat:<id>.PC1]``, ``[stat:<id>.PC2]``, ``[stat:<id>.samples]`` and
    ``[stat:<id>.groups]``. It also places each group on each component:
    ``[stat:<id>.<group> PC1 range]`` and ``[stat:<id>.<group> PC1 mean]``,
    and the same for PC2. Its statements say which pairs of groups each
    component separates, as their ranges on it do not overlap. Say them in
    your own words. Always write ``caption``: one sentence, in the
    researcher's words, saying what the plot shows.

    Args:
        ctx: Agent run context.
        identifier_variable: The gene column.
        value_variable: The measurement column, on the same entity.
        data_format: rawCounts for counts, normalizedValues otherwise.
        color_by_variable: The sample variable that colors the groups.
        caption: One sentence describing what the plot shows.
    """
    del ctx, identifier_variable, value_variable, data_format
    del color_by_variable, caption
    msg = "run_eda_dimensionality_reduction runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)


def _spec(spec: EdaVariableSpecIn) -> EdaVariableSpec:
    return EdaVariableSpec.model_validate(spec, from_attributes=True)


async def read_eda_statistics(
    ctx: RunContext[LeadDeps],
    *,
    kind: Literal["two_by_two", "contingency", "boxplot", "trend"],
    x_variable: EdaVariableSpecIn,
    y_variable: EdaVariableSpecIn,
    output_entity_id: str,
    x_reference_value: str | None = None,
    y_reference_value: str | None = None,
    color_by_variable: EdaVariableSpecIn | None = None,
    caption: str = "",
) -> ToolReturn[EdaStatisticResult]:
    """Have the site's EDA service compute one statistic on the open analysis.

    It runs on the analysis's own subset and returns at once. Pick the kind
    from the two variables:

    - ``two_by_two``: two categorical sample variables of two values each,
      as in "is infection status associated with sex". Name the exposed x
      value in ``x_reference_value`` and the positive y value in
      ``y_reference_value``. The service returns the table, chi-squared,
      Fisher's exact test, the odds ratio, the relative risk and more.
    - ``contingency``: two categorical variables, one with more than two
      values. The service returns the table and a chi-squared test.
    - ``boxplot``: a continuous ``y_variable`` by a categorical
      ``x_variable``; ``color_by_variable`` splits each group.
    - ``trend``: two continuous variables. The service fits a line and
      returns its r-squared.

    ``output_entity_id`` is the entity whose records are counted; both
    variables are on it or on an ancestor of it. The result carries a
    statistic id and the name of each row. State every value with
    ``[stat:<id>.<row name>]`` and never compute a number yourself. Always
    write ``caption``: one sentence saying what the statistic shows.

    Args:
        ctx: Agent run context.
        kind: The statistic the service computes.
        x_variable: The first variable, the groups of a boxplot.
        y_variable: The second variable, the values of a boxplot.
        output_entity_id: The entity whose records are counted.
        x_reference_value: The exposed x value of a two_by_two.
        y_reference_value: The positive y value of a two_by_two.
        color_by_variable: The variable that splits a boxplot's groups.
        caption: One sentence describing what the statistic shows.
    """
    site_id = ctx.deps.runtime.site_id
    bound = await bound_analysis(ctx)
    if bound is None:
        msg = (
            "This conversation has no study open, so there is no subset to "
            "compute on. Call open_eda_analysis first."
        )
        raise ModelRetry(msg)
    analysis = await read_analysis(site_id, analysis_id=bound.analysis_id)
    _entry, study = await get_study_detail_for_dataset(site_id, bound.dataset_id)
    request = StatisticsRequest(
        kind=kind,
        x=_spec(x_variable),
        y=_spec(y_variable),
        output_entity_id=output_entity_id,
        x_reference_value=x_reference_value,
        y_reference_value=y_reference_value,
        color_by=None if color_by_variable is None else _spec(color_by_variable),
    )
    try:
        part = await read_statistics_part(
            bound,
            study=study,
            filters=analysis.descriptor.subset.descriptor,
            request=request,
            caption=caption,
        )
    except StatisticsRefusedError as exc:
        msg = f"{exc} Nothing was computed."
        raise ModelRetry(msg) from exc
    fact = statistics_fact(part)
    ctx.deps.state.domain.record_statistics([fact])
    return with_summary(
        EdaStatisticResult(statistic=fact),
        part.title,
        ctx=ctx,
        extra=[eda_statistics_chunk(part)],
    )


__all__ = [
    "EDA_PCA",
    "EdaStatisticResult",
    "pca_statistic",
    "read_eda_statistics",
    "run_eda_dimensionality_reduction",
]
