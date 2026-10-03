"""What a bound criterion measures: the label of each pick, and the counts of
the other readings of each value the site or the model set."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.wdk import WDKSearch, phyletic_tree_of
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, ResolvedParams

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_count import record_and_count_criterion
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.strategy.measurement_clauses import measurement_clauses
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OpenSlot,
    ParameterAlternatives,
)
from pathfinder.services.strategies.cut_picks import read_picks
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    measure_binding,
)
from pathfinder.services.strategies.value_labels import vocabulary_labels


def _with_vocabulary(info: ParameterInfo, read: ParameterInfo) -> ParameterInfo:
    """The published entry holding the vocabulary another read answers."""
    return info.model_copy(
        update={
            "allowed_values": read.allowed_values,
            "allowed_values_total": read.allowed_values_total,
            "allowed_values_tree": read.allowed_values_tree,
            "allowed_values_note": read.allowed_values_note,
            "prompt_values": read.prompt_values,
            "vocab_leaves": read.vocab_leaves,
        }
    )


async def vocabularies_under(
    fetch_at: ParamFetcher, infos: list[ParameterInfo], values: Mapping[str, ParamValue]
) -> list[ParameterInfo]:
    """The published sheet with each dependent vocabulary as the bound parents
    answer it. WDK answers each sent value as its parameter's initial value, so
    the read gives vocabularies and nothing else."""
    if not any(info.vocab_depends_on for info in infos):
        return infos
    read = await fetch_at({name: to_wire(value) for name, value in values.items()})
    answered = {info.name: info for info in read}
    return [
        _with_vocabulary(info, answered[info.name])
        if info.vocab_depends_on and info.name in answered
        else info
        for info in infos
    ]


async def labelled_picks(
    fetch_at: ParamFetcher,
    infos: list[ParameterInfo],
    call: CriterionCall,
    bound: dict[str, BoundValue],
) -> list[Measurement]:
    """The label the vocabulary, read under the bound parents, gives each pick.
    A proposed pick or filter clause with no label is refused with the nearest
    labels; a value the site supplied is recorded as it is."""
    infos = await vocabularies_under(
        fetch_at, infos, {name: held.value for name, held in bound.items()}
    )
    read = vocabulary_labels(bound, infos)
    filters = {info.name for info in infos if info.param_kind == "filter"}
    proposed = [
        pick
        for pick in read.unlabelled
        if pick.param in filters
        or pick.term in proposal_values(call.params.get(pick.param))
    ]
    if proposed:
        pick = proposed[0]
        shown = next((i.display_name for i in infos if i.name == pick.param), "")
        msg = (
            f"{pick.param} ({shown}) on {call.search_name} holds {pick.term!r}, "
            f"which its vocabulary gives no label. Pass the entry of one of these "
            f"labels: {pick.labels}."
        )
        raise ModelRetry(msg)
    return read.labels


def display_names(
    bound: Mapping[str, BoundValue],
    open_params: Sequence[OpenSlot],
    infos: list[ParameterInfo],
) -> dict[str, str]:
    """The name the site shows each bound or open parameter by."""
    held = set(bound) | {slot.param_name for slot in open_params}
    return {info.name: info.display_name for info in infos if info.name in held}


async def record_measurements(
    ctx: RunContext[AgentDeps],
    criterion: Criterion,
    *,
    record_type: str,
    params: Mapping[str, ParamValue],
    count: int | None,
    definition: WDKSearch,
    infos: list[ParameterInfo],
) -> list[str]:
    """Record the counts of the other readings of the criterion's values, and
    answer every measurement it holds as a clause.

    ``params`` are the values the count sent. A binding that counted nothing
    records each value the site or the model set as not measured.
    """
    measured = await measure_binding(
        ctx.deps.agent_state.turn_counts,
        MeasuredBinding(
            site_id=ctx.deps.site_id,
            record_type=record_type,
            search_name=criterion.search_name,
            params=params,
            count=count,
            organism_param=criterion.organism_param,
        ),
        values=criterion.resolved_params,
        infos=infos,
        tree=phyletic_tree_of(definition.parameters or []),
    )
    overview = ctx.deps.agent_state.get_overview(criterion.search_name)
    reads = overview.options_reads() if overview else []
    measured = [*measured, *read_picks(criterion, reads)]
    state = ctx.deps.agent_state
    state.frame_record_measurements(criterion.id, measured)
    stored = next(
        c for c in state.operational_spec_draft.criteria if c.id == criterion.id
    )
    return measurement_clauses(stored, noun=counted_noun(record_type))


async def record_bound_criterion(
    ctx: RunContext[AgentDeps],
    criterion: Criterion,
    *,
    record_type: str,
    definition: WDKSearch,
    canonical: ResolvedParams,
    fetch_at: ParamFetcher,
    infos: list[ParameterInfo],
) -> tuple[int | None, list[ParameterAlternatives], list[str]]:
    """Record the criterion, count it, then measure its other readings under
    the sheet its bound parents answer."""
    count, alternatives = await record_and_count_criterion(
        ctx,
        criterion,
        record_type=record_type,
        definition=definition,
        resolved=canonical,
        infos=infos,
    )
    measured = await record_measurements(
        ctx,
        criterion,
        record_type=record_type,
        params=canonical.params,
        count=count,
        definition=definition,
        infos=await vocabularies_under(fetch_at, infos, criterion.param_values),
    )
    return count, alternatives, measured
