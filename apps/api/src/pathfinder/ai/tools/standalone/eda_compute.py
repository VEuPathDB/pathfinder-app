"""The durable differential-expression compute."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from assistant_core.graph.tool_summary import summary_chunks
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome
from pydantic import ConfigDict
from pydantic_ai import RunContext
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.platform.durable_worker import durable_agent_tool

_ESTIMATED_SECONDS = 120


class EdaVariableSpecIn(CamelModel):
    """One (entity, variable) pair, as the model writes it."""

    entity_id: str
    variable_id: str


class _ComputeOutcome(CamelModel):
    """The counts a finished differential expression reports."""

    model_config = ConfigDict(extra="ignore")

    genes_tested: int = 0
    retained_up: int = 0
    retained_down: int = 0


def _compute_chunks_from_result(
    resumed: Any,
    task_id: UUID,
    tool_call_id: str | None,
) -> list[BaseChunk]:
    del task_id
    outcome = DurableOutcome.model_validate(resumed)
    if not outcome.succeeded:
        return []
    counts = _ComputeOutcome.model_validate(outcome.result)
    retained = counts.retained_up + counts.retained_down
    return summary_chunks(
        tool_call_id,
        f"{counts.genes_tested:,} genes tested, {counts.retained_up:,} up "
        f"and {counts.retained_down:,} down",
        status="ok" if retained else "empty",
    )


EDA_COMPUTE = declare_durable_tool(
    tool_name="run_eda_compute",
    estimated_duration_seconds=_ESTIMATED_SECONDS,
    chunks_from_result=_compute_chunks_from_result,
)


@durable_agent_tool(EDA_COMPUTE)
async def run_eda_compute(
    ctx: RunContext[LeadDeps],
    *,
    identifier_variable: EdaVariableSpecIn,
    value_variable: EdaVariableSpecIn,
    comparator_variable: EdaVariableSpecIn,
    group_a_labels: list[str],
    group_b_labels: list[str],
    method: Literal["DESeq", "limma"] = "DESeq",
    caption: str = "",
) -> dict[str, Any]:
    """Run differential expression on the open EDA analysis, on the worker.

    This compares two groups of samples and reports, per gene, an effect size
    and a p-value. It runs in the background: the turn ends cleanly, the
    researcher sees progress, and you are called again with the result when it
    finishes. That can take a minute or several.

    Use it when the question is a comparison - "up in febrile samples",
    "different between the mutant and the wild type", "responds to heat shock".

    Choosing the arguments, and describe_eda_study gives you all of them:

    - ``identifier_variable`` is the gene column, and it is the reserved
      variable ``VEUPATHDB_GENE_ID``.
    - ``value_variable`` is the measurement column on the SAME entity. It is
      one of the reserved ids ``SEQUENCE_READ_COUNT``,
      ``SEQUENCE_READ_COUNT_SENSE``, ``SEQUENCE_READ_COUNT_ANTISENSE``,
      ``NORMALIZED_EXPRESSION`` or ``NORMALIZED_INTENSITY``.
    - ``comparator_variable`` is the sample-level variable that separates the
      two groups, and it lives on an ANCESTOR entity of the expression data.
    - ``group_a_labels`` is the reference group and ``group_b_labels`` is the
      comparison group. Every label must be a value in the comparator
      variable's vocabulary, and no label may be in both groups.
    - ``method`` is ``DESeq`` for raw counts and ``limma`` for normalized array
      data. ``DESeq2`` is not a value.

    The result carries the job's identity, the number of genes tested, and how
    many pass the default thresholds of effect size 1 and p-value 0.05, split
    into up and down. Tell the researcher those numbers, then use
    create_eda_step to export the ones that pass.

    Always write ``caption``. It is the one sentence printed under the plot,
    so it says what the comparison SHOWS in the researcher's terms - "Genes
    higher in febrile samples than in normal samples, per gene" - never an
    internal name and never a repeat of the numbers, which the figure already
    carries.

    Args:
        ctx: Agent run context.
        identifier_variable: The gene column.
        value_variable: The measurement column, on the same entity.
        comparator_variable: The sample variable separating the groups.
        group_a_labels: The reference group's vocabulary values.
        group_b_labels: The comparison group's vocabulary values.
        method: DESeq for counts, limma for normalized arrays.
        caption: One sentence describing what the comparison shows.
    """
    del (
        ctx,
        identifier_variable,
        value_variable,
        comparator_variable,
        group_a_labels,
        group_b_labels,
        method,
        caption,
    )
    msg = "run_eda_compute runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)
