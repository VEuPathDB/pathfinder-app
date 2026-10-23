"""The Lead tool that counts one built step's records by each value of one column."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.wdk import get_site

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._step_read import graph_step_id, read_as
from pathfinder.ai.tools.standalone.column_tally import tally_line
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.services.experiment.column_tally import (
    ColumnTally,
    ColumnTallyRefusedError,
)
from pathfinder.services.experiment.step_tally import CountedStep, run_step_tally


async def count_step_by_column(
    ctx: RunContext[LeadDeps], wdk_step_id: int, column: str
) -> ToolReturn[ColumnTally]:
    """Count one built step's records by each value of one column. Read-only.

    This answers "which <value> has the most <records>" over a result the
    strategy built, for example the proteins of a set of ortholog groups (the
    transform to proteins) counted by organism (``abbreviation``). The site
    counts the whole step in one request, with the column's value report where
    the site offers one. A column with only a word cloud is counted only when it
    holds genome codes (``abbreviation``), every word is a genome code and the
    counts sum to the step's records: the
    word cloud splits and folds values into words, so a matching sum alone does
    not prove that each word is one value. The table shows the 200 largest
    counts and links the step on the site; state the total with
    ``[tally:<id>]``, one value's count with ``[tally:<id>.<value>]`` and the
    number of values with ``[tally:<id>:values]``. Any other column is refused
    with the columns that can be counted.

    Args:
        wdk_step_id: The WDK step ID of a built step of this strategy.
        column: The column whose values are counted.
    """
    session = ctx.deps.strategy_session
    if graph_step_id(session, wdk_step_id) is None:
        held = ", ".join(str(step) for step in session.wdk_step_ids())
        built = (
            f"Its built steps: {held}."
            if held
            else "This strategy has no built step yet."
        )
        msg = f"Step {wdk_step_id} is not a step of this strategy. {built}"
        raise ModelRetry(msg)
    record_type, own_search = await read_as(session, wdk_step_id)
    sync = session.sync_state
    strategy_id = None if sync is None else sync.wdk_strategy_id
    step_url = (
        None
        if strategy_id is None
        else get_site(session.site_id).strategy_url(strategy_id, wdk_step_id)
    )
    refused = ctx.deps.refused_tally_columns.setdefault(wdk_step_id, set())
    try:
        tally = await run_step_tally(
            CountedStep(
                site_id=session.site_id,
                wdk_step_id=wdk_step_id,
                record_type=record_type,
                search_name=own_search or "",
                record_noun=counted_noun(record_type),
                step_url=step_url,
                refused=frozenset(refused),
            ),
            column,
        )
    except ColumnTallyRefusedError as refusal:
        refused.add(column)
        raise ModelRetry(str(refusal)) from refusal
    ctx.deps.state.turn_markers.record_tally(tally.fact())
    chunk = DataChunk(
        type="data-column-tally", data=tally.model_dump(by_alias=True, mode="json")
    )
    return with_summary(tally, tally_line(tally), ctx=ctx, extra=[chunk])
