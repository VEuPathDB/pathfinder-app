"""What a criterion records when it binds: the criterion, its size, its choices."""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.graph.stream_events import ToolSummaryStatus
from assistant_core.graph.tool_summary import count_noun
from pydantic import JsonValue, RootModel, model_validator
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain.parameters import ParamKind, ParamValue
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, ResolvedParams

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.graph_helpers import counted_records
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    ParameterAlternatives,
)
from pathfinder.services.strategies.obsolete_terms import obsolete_picks
from pathfinder.services.strategies.wdk_counts import count_bound_criterion

# A vocabulary of this size is a choice a reader holds in mind; a larger one is
# a catalog to query, so it is reported by its size and not by its entries.
MAX_LISTED_OPTIONS = 10

_VOCABULARY_KINDS: frozenset[ParamKind] = frozenset(
    {"single-pick-vocabulary", "multi-pick-vocabulary"}
)


class _BoundTerms(RootModel[list[str]]):
    """The vocabulary terms one bound value selects, one pick or many."""

    @model_validator(mode="before")
    @classmethod
    def _as_terms(cls, raw: JsonValue) -> JsonValue:
        return raw if isinstance(raw, list) else [raw]


async def bound_count(
    ctx: RunContext[AgentDeps],
    resolved: ResolvedParams,
    record_type: str,
    search_name: str,
    definition: WDKSearch,
) -> int | None:
    """The records the completed binding matches.

    A search that runs on another step answers nothing until that step exists,
    and an open slot leaves a parameter unbound. None is a count that did not
    arrive in time. A count the site refuses with an error status refuses the
    binding, because the site cannot run the search at these values.
    """
    if resolved.open_slots or definition.allowed_primary_input_record_class_names:
        return None
    try:
        return await count_bound_criterion(
            ctx.deps.site_id, record_type, search_name, resolved.params
        )
    except WDKError as refused:
        msg = (
            f"The site refused to run {search_name} at these values "
            f"(HTTP {refused.status}: {refused.detail}). The criterion is not "
            f"bound. Bind another search for this requirement, or other values."
        )
        raise ModelRetry(msg) from refused


def _offered_by(info: ParameterInfo, value: ParamValue) -> ParameterAlternatives | None:
    """What one bound vocabulary parameter holds beyond the values it took.

    A parameter holding no value states no choice. The rest of the option list
    is the complement only when every value bound is itself an option, so a
    term that stands for others (a tree parent) reports the size alone.
    """
    bound = _BoundTerms.model_validate(value.to_decoded()).root
    if not bound:
        return None
    options = info.vocabulary()
    taken = set(bound)
    others = [option.value for option in options if option.value not in taken]
    if not others:
        return None
    complete = taken <= {option.value for option in options}
    listed = complete and len(options) <= MAX_LISTED_OPTIONS
    return ParameterAlternatives(
        param_name=info.name,
        bound=bound,
        option_count=len(options),
        other_options=others if listed else [],
    )


def empty_binding_alternatives(
    result_count: int | None,
    infos: Sequence[ParameterInfo],
    criterion: Criterion,
) -> list[ParameterAlternatives]:
    """The choices inside a binding that matches no record, on the parameters
    the site shows.

    A binding that matches records, and one whose count did not arrive, offers
    nothing to report.
    """
    if result_count != 0:
        return []
    shown = criterion.shown_values
    offered = [
        _offered_by(info, shown[info.name].value)
        for info in infos
        if info.param_kind in _VOCABULARY_KINDS and info.name in shown
    ]
    return [entry for entry in offered if entry is not None]


def _refuse_an_empty_obsolete_pick(
    criterion: Criterion, infos: Sequence[ParameterInfo], record_type: str
) -> None:
    """Refuse a binding that counts nothing and holds a pick the site labels
    obsolete, unless the site set that pick."""
    shown = {info.name: info.display_name for info in infos}
    for pick in obsolete_picks(criterion.measurements, infos):
        held = criterion.resolved_params[pick.param]
        if held.source == "default":
            continue
        raise ModelRetry(
            pick.refusal(
                criterion.search_name,
                shown[pick.param],
                counted=counted_records(0, record_type),
                researchers=held.source in {"stated", "card"},
            )
        )


async def record_and_count_criterion(
    ctx: RunContext[AgentDeps],
    criterion: Criterion,
    *,
    record_type: str,
    definition: WDKSearch,
    resolved: ResolvedParams,
    infos: Sequence[ParameterInfo],
) -> tuple[int | None, list[ParameterAlternatives]]:
    """Count the binding, then record the criterion with that count.

    A count the site refuses records nothing, and so does a count of zero on
    a pick the site labels obsolete. A count that did not arrive records the
    criterion with no count.
    """
    count = await bound_count(
        ctx, resolved, record_type, criterion.search_name, definition
    )
    if count == 0:
        _refuse_an_empty_obsolete_pick(criterion, infos, record_type)
    state = ctx.deps.agent_state
    state.frame_set_criterion(criterion)
    alternatives = empty_binding_alternatives(count, infos, criterion)
    state.frame_record_count(criterion.id, count, alternatives)
    return count, alternatives


def criterion_line(
    criterion_id: str,
    search_name: str,
    record_type: str,
    result_count: int | None,
    alternatives: Sequence[ParameterAlternatives],
) -> tuple[str, ToolSummaryStatus]:
    """The summary line a bound criterion writes, and the status it carries."""
    bound = f"{criterion_id} set to {search_name}"
    if result_count is None:
        return bound, "ok"
    line = f"{bound}, {counted_records(result_count, record_type)}"
    if alternatives:
        choices = ", ".join(
            f"{entry.param_name} has {count_noun(entry.option_count, 'option')}"
            for entry in alternatives
        )
        line = f"{line}; {choices}"
    return line, "ok" if result_count else "empty"


__all__ = [
    "MAX_LISTED_OPTIONS",
    "bound_count",
    "criterion_line",
    "empty_binding_alternatives",
    "record_and_count_criterion",
]
