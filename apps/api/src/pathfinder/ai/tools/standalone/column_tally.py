"""The Lead tool that counts one catalog search's records by each value of one
column, without a step."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.ai.tools.standalone.search_reads import resolved_search
from pathfinder.services.experiment.column_tally import (
    ColumnTally,
    ColumnTallyRefusedError,
    TallyOnly,
    run_column_tally,
)
from pathfinder.services.experiment.variant_comparison import VariantInput


def _line(tally: ColumnTally) -> str:
    top = tally.rows[0] if tally.rows else None
    most = "" if top is None else f", most {top.value} ({top.count:,})"
    return f"{tally.title}: {tally.distinct:,} values{most}"


async def count_by_column(
    ctx: RunContext[LeadDeps],
    search: VariantInput,
    column: str,
    only_column: str | None = None,
    only_values: list[str] | None = None,
) -> ToolReturn[ColumnTally]:
    """Count one catalog search's records by each value of one column. Read-only.

    This answers "which <value> has the most <records>" and "how many <records>
    per <value>": the site's own column reporter counts the whole result in one
    request, and no step is added. ``only_column`` and ``only_values`` keep only
    the rows whose ``only_column`` is one of ``only_values`` before the count,
    for example the RNA-Seq datasets (``newcategory`` is ``RNASeq``) counted by
    organism (``organism_prefix``). A value that lists several entries counts as
    one value of its own. The table shows every count; state the total with
    ``[tally:<id>]`` and one value's count with ``[tally:<id>.<value>]``. A
    column the site cannot count is refused with the columns it can.

    Args:
        search: The search, its parameter values and a short ``label``.
        column: The column whose values are counted.
        only_column: The column that keeps the rows counted, with ``only_values``.
        only_values: The values of ``only_column`` the rows counted hold.
    """
    if (only_column is None) != (not only_values):
        msg = "Name only_column and only_values together, or neither."
        raise ModelRetry(msg)
    only = (
        None
        if only_column is None or not only_values
        else TallyOnly(column=only_column, values=only_values)
    )
    spec = await resolved_search(ctx, search)
    try:
        tally = await run_column_tally(
            ctx.deps.site_id,
            spec,
            column,
            only,
            record_noun=counted_noun(spec.record_type),
        )
    except ColumnTallyRefusedError as refused:
        raise ModelRetry(str(refused)) from refused
    ctx.deps.state.turn_markers.record_tally(tally.fact())
    chunk = DataChunk(
        type="data-column-tally", data=tally.model_dump(by_alias=True, mode="json")
    )
    return with_summary(tally, _line(tally), ctx=ctx, extra=[chunk])
