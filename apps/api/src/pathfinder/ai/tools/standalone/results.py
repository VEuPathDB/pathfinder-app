"""The tools that read a built step's columns and a sample of its records."""

import asyncio
from dataclasses import dataclass
from functools import partial
from typing import Annotated

from assistant_core.graph.tool_summary import with_summary
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.domain import SearchContext
from veupathdb.domain.strategy import walk
from veupathdb.wdk import (
    get_strategy_api,
)
from veupathdb_mcp.catalog import (
    get_discovery_service,
    get_raw_record_types,
    get_raw_searches,
)
from veupathdb_mcp.tool_payloads import gene_sample_attributes

from pathfinder.ai.capabilities.site_reads import read_in_time
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._expression_check import read_expression_fit
from pathfinder.ai.tools.standalone._result_models import (
    MAX_SAMPLE_LIMIT,
    StepColumns,
    _validate_sample_inputs,
    no_column,
    no_rows,
)
from pathfinder.ai.tools.standalone._sample_attributes import sample_attributes
from pathfinder.ai.tools.standalone._sample_page import (
    SampledRecords,
    StepSample,
    sample_page,
)
from pathfinder.ai.tools.standalone._step_columns import (
    AttributeHistogram,
    ColumnBound,
    bound_param_value,
    by_value_bins,
    column_bounds,
    measured,
    settled,
)
from pathfinder.ai.tools.standalone._step_read import graph_step_id, read_as
from pathfinder.domain.evidence import ColumnFit, CountedIn
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.domain.strategy.types import SyncStateProtocol

# A read of a few rows or of one column answers in about a second; a site that
# takes longer holds the whole check, which goes on without the read instead.
READ_DEADLINE_SECONDS = 20.0


def sample_seed(wdk_step_id: int, answer: str) -> str:
    """The seed of one step's sample, while the step answers ``answer``."""
    return f"{wdk_step_id}:{answer}"


def named_or_root(sync_state: SyncStateProtocol | None, wdk_step_id: int | None) -> int:
    """The step a read names, else the root of the built strategy."""
    if wdk_step_id is not None:
        return wdk_step_id
    root = None if sync_state is None else sync_state.wdk_root_step_id
    if root is None:
        msg = (
            "This conversation's strategy has no built root yet, so no step holds "
            "genes to read."
        )
        raise ModelRetry(msg)
    return root


def _step_answer(session: StrategySession, wdk_step_id: int) -> str:
    """The revision of what the step computes: its search, values and inputs.

    Empty when the strategy holds no step with that WDK id.
    """
    graph = session.get_graph(None)
    ast = None if graph is None else graph.to_strategy_ast()
    step_id = graph_step_id(session, wdk_step_id)
    node = (
        None
        if ast is None
        else next((n for n in walk(ast.root) if n.id == step_id), None)
    )
    if ast is None or node is None:
        return ""
    return strategy_revision(
        ast.model_copy(update={"root": node, "detached_roots": []})
    )


def step_sample_seed(session: StrategySession, wdk_step_id: int) -> str:
    """The seed of the step's sample while it computes what it computes now."""
    return sample_seed(wdk_step_id, _step_answer(session, wdk_step_id))


async def _sample(
    session: StrategySession, wdk_step_id: int, limit: int
) -> SampledRecords:
    """The step's sample, with the attributes the strategy's searches select on
    and the columns the step's own search shows."""
    record_type, own_search = read_as(session, wdk_step_id)
    attributes = [
        *(gene_sample_attributes(record_type) or []),
        *await sample_attributes(
            session.site_id,
            record_type,
            session.get_graph(None),
            own_search=own_search,
        ),
    ]
    return await sample_page(
        session.site_id,
        wdk_step_id,
        limit=limit,
        attributes=list(dict.fromkeys(attributes)) or None,
        record_type=record_type,
        seed=step_sample_seed(session, wdk_step_id),
    )


async def get_sample_records(
    ctx: RunContext[AgentDeps],
    wdk_step_id: int | None = None,
    limit: Annotated[int, Field(ge=1, le=MAX_SAMPLE_LIMIT)] = 5,
) -> ToolReturn[StepSample]:
    """Get a sample of records from an executed step, spread over the step.

    The step must already be built in WDK. Returns N records, one per gene,
    spread over the step: one report when the step holds at most ten records
    per sampled gene, else at most 4 reports, one window in each quarter. The
    same call answers the same records while the step's answer is unchanged,
    in this message or a later one. Each carries its id plus, for
    gene/transcript steps, the product description, gene symbol, and
    organism, the attributes the strategy's searches select on, and the
    columns the step's own search shows, such as a BLAST hit's ``evalue`` and
    ``score``, as the site states them. An attribute the site refuses is left
    out of every row and of ``attributes`` and named in ``droppedAttributes``.
    Read a step's columns with ``read_step_columns`` first; sample only for a
    criterion no column shows.

    Args:
        wdk_step_id: WDK step ID of a built step. Leave it out for the root,
            which holds the result the researcher sees; name another step only
            when the researcher names that step.
        limit: Number of records to return, at most 100.
    """
    session = ctx.deps.strategy_session
    wdk_step_id = named_or_root(session.sync_state, wdk_step_id)
    _validate_sample_inputs(wdk_step_id)

    sample = await read_in_time(
        "get_sample_records",
        f"step {wdk_step_id}",
        _sample(session, wdk_step_id, limit),
        deadline=READ_DEADLINE_SECONDS,
    )
    ctx.deps.turn_markers.record_sampled_genes(sample.gene_ids)
    ctx.deps.turn_markers.record_listed_genes(wdk_step_id, sample.gene_ids)
    return with_summary(
        sample.result,
        f"{len(sample.result.records)} sample records from step {wdk_step_id}",
        ctx=ctx,
    )


@dataclass(frozen=True)
class _SearchStep:
    criterion: Criterion
    search_name: str
    record_type: str | None
    # The records the site counts in the step, None before it counts them.
    count: int | None = None


def _search_step(ctx: RunContext[AgentDeps], wdk_step_id: int) -> _SearchStep | None:
    """The criterion whose search the step runs, or None for any other step."""
    session = ctx.deps.strategy_session
    sync, graph = session.sync_state, session.get_graph(None)
    if sync is None or graph is None:
        return None
    step_id = next((s for s, w in sync.wdk_step_ids.items() if w == wdk_step_id), None)
    step = None if step_id is None else graph.steps.get(step_id)
    criteria = ctx.deps.agent_state.operational_spec_draft.criteria
    criterion = next((c for c in criteria if c.id == step_id), None)
    if step is None or not step.search_name or criterion is None:
        return None
    return _SearchStep(
        criterion=criterion,
        search_name=step.search_name,
        record_type=graph.record_type,
        count=sync.step_counts.get(criterion.id),
    )


async def _column_bounds(site_id: str, target: _SearchStep) -> list[ColumnBound]:
    searches = await get_raw_searches(site_id, "transcript")
    record = next(
        (
            r
            for r in await get_raw_record_types(site_id)
            if r.url_segment == "transcript"
        ),
        None,
    )
    search = next((s for s in searches if s.url_segment == target.search_name), None)
    if record is None or search is None:
        return []
    definition = await get_discovery_service().get_search_details(
        SearchContext(
            site_id=site_id, record_type="transcript", search_name=target.search_name
        )
    )
    fields = record.attributes or list((record.attributes_map or {}).values())
    return column_bounds(
        search,
        definition.search_data.parameters or [],
        fields,
        searches,
        partial(bound_param_value, target.criterion),
    )


async def read_column_fit(
    site_id: str, wdk_step_id: int, criterion: Criterion, bound: ColumnBound
) -> ColumnFit:
    """One report over the whole step, counted against the bound's thresholds."""
    api = get_strategy_api(site_id)
    counted_in: CountedIn = "genes"
    if bound.histogram is not None:
        report = await api.run_step_report(wdk_step_id, bound.histogram)
        bins, counted_in = (
            AttributeHistogram.model_validate(report).bins(),
            "transcripts",
        )
    else:
        distribution = await api.get_column_distribution(wdk_step_id, bound.column)
        bins = by_value_bins(distribution)
    read = measured(bound, bins)
    return ColumnFit(
        criterion_id=criterion.id,
        criterion_text=criterion.text,
        wdk_step_id=wdk_step_id,
        column=bound.column,
        display_name=bound.display_name,
        bound_value=read.bound_value,
        counted_in=counted_in,
        total=read.total,
        fitting=read.fitting,
        fitting_at_most=read.fitting_at_most,
        shown=bool(bins),
        sides=list(read.sides),
    )


async def _read_columns(
    ctx: RunContext[AgentDeps], wdk_step_id: int, target: _SearchStep | None
) -> tuple[StepColumns, str]:
    site_id = ctx.deps.strategy_session.site_id
    if target is None or target.record_type != "transcript":
        return no_column(
            wdk_step_id,
            f"Step {wdk_step_id} is not a gene search step a criterion binds.",
        )
    bounds = await _column_bounds(site_id, target)
    if not bounds:
        return no_column(
            wdk_step_id,
            f"No column of {target.search_name} shows a numeric value its "
            "criterion binds.",
        )
    read = await read_in_time(
        "read_step_columns",
        f"step {wdk_step_id}",
        asyncio.gather(
            *(
                read_column_fit(site_id, wdk_step_id, target.criterion, b)
                for b in bounds
            )
        ),
        deadline=READ_DEADLINE_SECONDS,
    )
    unread = [fit for fit in read if not fit.shown]
    if unread and target.count:
        return no_rows(wdk_step_id, target.count, unread)
    fits = settled(list(zip(bounds, read, strict=True)))
    if not fits:
        return no_column(
            wdk_step_id,
            f"{len(bounds)} columns of {target.search_name} may show the bound "
            "values and they do not all hold every gene inside them.",
        )
    ctx.deps.turn_markers.record_column_fits(fits)
    return StepColumns(wdk_step_id=wdk_step_id, fits=fits), "; ".join(
        fit.sentence for fit in fits
    )


async def read_step_columns(
    ctx: RunContext[AgentDeps],
    wdk_step_id: int,
) -> ToolReturn[StepColumns]:
    """Read the columns a search step shows for the numeric values its criterion binds.

    Each column is one report over the whole step: how many of its genes hold
    a value inside the bounds, such as ``tm_count`` 2 to 99, and for a threshold
    whose direction the site does not state, how many lie on each side. A step
    whose search shows no such column, or several that do not all hold every
    gene, says so, and only then is the root sampled. A column whose read
    returns no rows for a step the site counts names the step to sample.

    On an OrthoMCL group step whose criterion binds ``phyletic_expression``,
    the answer is ``expression_fit`` alone: the step's first groups, with their
    proteins per genome, judged against the expression as the site reads it,
    or, on a step that holds no group, each unit the site matches no group
    with. That fit judges the criterion, so the step needs no sample.

    Args:
        wdk_step_id: The WDK step id of a search step, not a combine.
    """
    target = _search_step(ctx, wdk_step_id)
    fit = (
        None
        if target is None
        else await read_in_time(
            "read_step_columns",
            f"step {wdk_step_id}",
            read_expression_fit(
                ctx.deps.strategy_session.site_id, wdk_step_id, target.criterion
            ),
            deadline=READ_DEADLINE_SECONDS,
        )
    )
    if fit is not None:
        ctx.deps.turn_markers.record_expression_fit(fit)
        judged = StepColumns(wdk_step_id=wdk_step_id, expression_fit=fit)
        return with_summary(judged, fit.sentence, ctx=ctx)
    columns, summary = await _read_columns(ctx, wdk_step_id, target)
    return with_summary(columns, summary, ctx=ctx)
