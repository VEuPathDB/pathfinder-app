"""Standalone result tools for pydantic-ai agents.

Provides:
- ``read_step_columns`` -- read a search step's columns against its bound values
- ``get_sample_records`` -- get a sample of records spread over a step
"""

import asyncio
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from itertools import pairwise
from typing import Annotated

from assistant_core.graph.tool_summary import with_summary
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb import JSONObject, strip_html_tags
from veupathdb.domain import SearchContext
from veupathdb.domain.strategy import walk
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import (
    StrategyAPI,
    WDKAnswer,
    WDKFilterValue,
    WDKRecordInstance,
    get_strategy_api,
)
from veupathdb_mcp.catalog import (
    get_discovery_service,
    get_raw_record_types,
    get_raw_searches,
)
from veupathdb_mcp.tool_payloads import gene_sample_attributes
from veupathdb_mcp.wdk import (
    SampleRecordsResult,
    extract_pk,
    view_filters_for,
)

from pathfinder.ai.capabilities.site_reads import site_read_failure, site_words
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._result_models import (
    MAX_SAMPLE_LIMIT,
    StepColumns,
    _validate_sample_inputs,
)
from pathfinder.ai.tools.standalone._sample_attributes import sample_attributes
from pathfinder.ai.tools.standalone._step_columns import (
    AttributeHistogram,
    ColumnBound,
    bound_param_value,
    by_value_bins,
    column_bounds,
    measured,
    settled,
)
from pathfinder.domain.evidence import ColumnFit, CountedIn
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.domain.strategy.types import SyncStateProtocol

# A read of a few rows or of one column answers in about a second; a site that
# takes longer holds the whole check, which goes on without the read instead.
READ_DEADLINE_SECONDS = 20.0


@dataclass(frozen=True)
class SampledRecords:
    """One page of a step's records, and the gene each row names."""

    result: SampleRecordsResult
    gene_ids: list[str]


def _row(record: WDKRecordInstance, attributes: list[str]) -> JSONObject:
    texts: JSONObject = {
        name: None
        if (text := record.attribute_text(name)) is None
        else strip_html_tags(text)
        for name in attributes
    }
    return {"id": record.display_name, **texts}


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
    sync = session.sync_state
    graph = session.get_graph(None)
    ast = None if graph is None else graph.to_strategy_ast()
    step_id = next(
        (
            s
            for s, w in ({} if sync is None else sync.wdk_step_ids).items()
            if w == wdk_step_id
        ),
        None,
    )
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


def spread_offsets(total: int, limit: int, *, seed: str) -> list[int]:
    """One offset in each of ``limit`` equal strides of the step, placed within
    its stride by the seed, so one seed always reads the same records."""
    count = min(limit, total)
    if count == 0:
        return []
    starts = [i * total // count for i in range(count + 1)]
    return [
        start + _drawn(f"{seed}:{index}") % (end - start)
        for index, (start, end) in enumerate(pairwise(starts))
    ]


def _drawn(key: str) -> int:
    return int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest())


async def _record_at(
    api: StrategyAPI,
    step_id: int,
    offset: int,
    *,
    attributes: list[str] | None,
    view: Sequence[WDKFilterValue] | None,
) -> WDKAnswer:
    page = {"offset": offset, "numRecords": 1}
    try:
        return await api.get_step_records(
            step_id, attributes=attributes, pagination=page, view_filters=view
        )
    except VEuPathDBError:
        # A record class that lacks the attributes still answers its ids.
        return await api.get_step_records(step_id, pagination=page, view_filters=view)


async def sample_page(
    site_id: str,
    step_id: int,
    *,
    limit: int,
    attributes: list[str] | None,
    record_type: str,
    seed: str,
) -> SampledRecords:
    """The step's records at offsets spread over the whole step, one row per
    gene, placed by the seed."""
    api = get_strategy_api(site_id)
    view = view_filters_for(record_type)
    counted = await api.get_step_records(
        step_id, pagination={"offset": 0, "numRecords": 0}, view_filters=view
    )
    total = counted.meta.records_returned()
    answers = await asyncio.gather(
        *(
            _record_at(api, step_id, offset, attributes=attributes, view=view)
            for offset in spread_offsets(total, limit, seed=seed)
        )
    )
    records = [record for answer in answers for record in answer.records]
    shown = [] if not answers else list(answers[0].meta.attributes)
    return SampledRecords(
        result=SampleRecordsResult(
            step_id=step_id,
            total_count=total,
            records=[_row(record, shown) for record in records],
            attributes=shown,
        ),
        gene_ids=[extract_pk(r) or r.display_name for r in records],
    )


async def get_sample_records(
    ctx: RunContext[AgentDeps],
    wdk_step_id: int | None = None,
    limit: Annotated[int, Field(ge=1, le=MAX_SAMPLE_LIMIT)] = 5,
) -> ToolReturn[SampleRecordsResult]:
    """Get a sample of records from an executed step, spread over the whole step.

    The step must already be built in WDK. Returns N records, one per gene,
    each read at its own offset and the offsets spread over the step. The same
    call answers the same records while the step's answer is unchanged, in this
    message or a later one. Each
    carries its id plus, for gene/transcript steps, the product description,
    gene symbol, and organism, and the attributes the strategy's searches select on, as the site states
    them. Read a step's columns with ``read_step_columns`` first; sample only
    for a criterion no column shows.

    Args:
        wdk_step_id: WDK step ID of a built step. Leave it out for the root,
            which holds the result the researcher sees; name another step only
            when the researcher names that step.
        limit: Number of records to return, at most 100.
    """
    session = ctx.deps.strategy_session
    wdk_step_id = named_or_root(session.sync_state, wdk_step_id)
    _validate_sample_inputs(wdk_step_id)

    graph = session.get_graph(None)
    record_type = (graph.record_type if graph is not None else None) or "transcript"
    try:
        attributes = [
            *(gene_sample_attributes(record_type) or []),
            *await sample_attributes(session.site_id, record_type, graph),
        ]
        sample = await asyncio.wait_for(
            sample_page(
                session.site_id,
                wdk_step_id,
                limit=limit,
                attributes=attributes or None,
                record_type=record_type,
                seed=step_sample_seed(session, wdk_step_id),
            ),
            timeout=READ_DEADLINE_SECONDS,
        )
    except TimeoutError as exc:
        said = f"no answer within {READ_DEADLINE_SECONDS} s for step {wdk_step_id}"
        raise site_read_failure("get_sample_records", said) from exc
    except (VEuPathDBError, OSError) as exc:
        raise site_read_failure("get_sample_records", site_words(exc)) from exc
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


def _search_step(ctx: RunContext[AgentDeps], wdk_step_id: int) -> _SearchStep | None:
    """The criterion whose search the step runs, or None for any other step."""
    session = ctx.deps.strategy_session
    sync, graph = session.sync_state, session.get_graph(None)
    if sync is None or graph is None or graph.record_type != "transcript":
        return None
    step_id = next((s for s, w in sync.wdk_step_ids.items() if w == wdk_step_id), None)
    step = None if step_id is None else graph.steps.get(step_id)
    criteria = ctx.deps.agent_state.operational_spec_draft.criteria
    criterion = next((c for c in criteria if c.id == step_id), None)
    if step is None or not step.search_name or criterion is None:
        return None
    return _SearchStep(criterion=criterion, search_name=step.search_name)


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


def _no_column(
    ctx: RunContext[AgentDeps], wdk_step_id: int, why: str
) -> ToolReturn[StepColumns]:
    return with_summary(
        StepColumns(
            wdk_step_id=wdk_step_id,
            note=f"{why} Sample the root with get_sample_records for this criterion.",
        ),
        f"No column of step {wdk_step_id}",
        ctx=ctx,
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
    gene, says so, and only then is the root sampled.

    Args:
        wdk_step_id: The WDK step id of a search step, not a combine.
    """
    site_id = ctx.deps.strategy_session.site_id
    target = _search_step(ctx, wdk_step_id)
    if target is None:
        return _no_column(
            ctx,
            wdk_step_id,
            f"Step {wdk_step_id} is not a gene search step a criterion binds.",
        )
    bounds = await _column_bounds(site_id, target)
    if not bounds:
        return _no_column(
            ctx,
            wdk_step_id,
            f"No column of {target.search_name} shows a numeric value its "
            "criterion binds.",
        )
    try:
        read = await asyncio.wait_for(
            asyncio.gather(
                *(
                    read_column_fit(site_id, wdk_step_id, target.criterion, b)
                    for b in bounds
                )
            ),
            timeout=READ_DEADLINE_SECONDS,
        )
    except (TimeoutError, VEuPathDBError, OSError) as exc:
        raise site_read_failure("read_step_columns", site_words(exc)) from exc
    fits = settled(list(zip(bounds, read, strict=True)))
    if not fits:
        return _no_column(
            ctx,
            wdk_step_id,
            f"{len(bounds)} columns of {target.search_name} may show the bound "
            "values and they do not all hold every gene inside them.",
        )
    ctx.deps.turn_markers.record_column_fits(fits)
    return with_summary(
        StepColumns(wdk_step_id=wdk_step_id, fits=fits),
        "; ".join(fit.sentence for fit in fits),
        ctx=ctx,
    )
