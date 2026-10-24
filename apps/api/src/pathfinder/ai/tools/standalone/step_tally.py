"""The Lead tools that list a built step's columns and count the step's records
by each value of one of them."""

from __future__ import annotations

from typing import Annotated

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.wdk import get_site
from veupathdb_mcp.wdk import (
    DEFAULT_COLUMN_COUNT_TOP,
    MAX_COLUMN_COUNT_TOP,
    StepColumn,
)

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._step_read import graph_step_id, read_as
from pathfinder.ai.tools.standalone.column_tally import tally_line
from pathfinder.ai.tools.standalone.graph_helpers import record_noun
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.experiment.column_tally import (
    ColumnTally,
    ColumnTallyRefusedError,
)
from pathfinder.services.experiment.step_tally import (
    CountedStep,
    countable_columns,
    run_step_tally,
)

COLUMN_PAGE = 100


class StepColumnPage(CamelModel):
    """One page of a built step's columns, each with whether it can be counted."""

    wdk_step_id: int
    record_type: str
    search_name: str
    total: int
    countable: int
    offset: int
    columns: list[StepColumn]


def _require_strategy_step(session: StrategySession, wdk_step_id: int) -> None:
    if graph_step_id(session, wdk_step_id) is not None:
        return
    held = ", ".join(str(step) for step in session.wdk_step_ids())
    built = (
        f"Its built steps: {held}." if held else "This strategy has no built step yet."
    )
    msg = f"Step {wdk_step_id} is not a step of this strategy. {built}"
    raise ModelRetry(msg)


async def step_columns(
    ctx: RunContext[LeadDeps],
    wdk_step_id: int,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> ToolReturn[StepColumnPage]:
    """List the columns of one built step of this strategy and which can be counted.

    Call this before ``count_step_by_column``: it names the columns the step's
    records carry, its record type's columns and the columns its own search adds,
    such as a BLAST step's ``evalue``, each with its display name, its data type
    and ``countable``. Only a column marked ``countable`` can be counted. Any step
    of the strategy can be listed, a transform or a combine included; its columns
    are those of the records it holds. A step lists up to thousands of columns,
    100 per page in the site's order; ``total`` is the number of columns and
    ``offset`` reads the next page.

    Args:
        wdk_step_id: The WDK step ID of a built step of this strategy.
        offset: The first column of the page, 0 for the first page.
    """
    session = ctx.deps.strategy_session
    _require_strategy_step(session, wdk_step_id)
    listed = await countable_columns(session.site_id, wdk_step_id)
    page = StepColumnPage(
        wdk_step_id=wdk_step_id,
        record_type=listed.record_type,
        search_name=listed.search_name,
        total=len(listed.columns),
        countable=len(listed.countable_names()),
        offset=offset,
        columns=list(listed.columns[offset : offset + COLUMN_PAGE]),
    )
    summary = (
        f"{page.countable:,} of {page.total:,} columns of step {wdk_step_id} "
        "can be counted"
    )
    return with_summary(page, summary, ctx=ctx)


async def count_step_by_column(
    ctx: RunContext[LeadDeps],
    wdk_step_id: int,
    column: str,
    top: Annotated[
        int, Field(ge=1, le=MAX_COLUMN_COUNT_TOP)
    ] = DEFAULT_COLUMN_COUNT_TOP,
) -> ToolReturn[ColumnTally]:
    """Count one built step's records by each value of one column. Read-only.

    This answers "which <value> has the most <records>" and "how many <records>
    per <value>" over a result the strategy built, for example the proteins of a
    set of ortholog groups (the transform to proteins) counted by organism
    (``abbreviation``). List the step's columns with ``step_columns`` first and
    count one it marks ``countable``. The site counts the whole step in one
    request. It counts the step's records, not genes: on a transcript step a gene
    counts once per transcript, so a gene with two transcripts counts twice. A
    text column answers its values ranked by count, at most ``top``, beside the
    number of values; a number column answers its bins. A column with only a word
    cloud is counted only when it holds genome codes (``abbreviation``), every
    word is a genome code and the counts sum to the step's records. The table
    links the step on the site; state the total with ``[tally:<id>]``, one value's
    count with ``[tally:<id>.<value>]`` and the number of values with
    ``[tally:<id>:values]``. A column that cannot be counted is refused with the
    columns that can.

    Args:
        wdk_step_id: The WDK step ID of a built step of this strategy.
        column: The column whose values are counted, as ``step_columns`` names it.
        top: The most values shown, from 1 to 200.
    """
    session = ctx.deps.strategy_session
    _require_strategy_step(session, wdk_step_id)
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
                record_noun=record_noun(record_type),
                step_url=step_url,
                refused=frozenset(refused),
            ),
            column,
            top,
        )
    except ColumnTallyRefusedError as refusal:
        refused.add(column)
        raise ModelRetry(str(refusal)) from refusal
    ctx.deps.state.turn_markers.record_tally(tally.fact())
    chunk = DataChunk(
        type="data-column-tally", data=tally.model_dump(by_alias=True, mode="json")
    )
    return with_summary(tally, tally_line(tally), ctx=ctx, extra=[chunk])
