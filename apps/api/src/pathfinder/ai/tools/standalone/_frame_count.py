"""What a criterion records when it binds: the criterion, its size, its choices."""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.graph.stream_events import ToolSummaryStatus
from assistant_core.graph.tool_summary import count_noun
from pydantic import JsonValue, RootModel, model_validator
from pydantic_ai import RunContext
from veupathdb.domain.parameters import ParamKind, ParamValue
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, ResolvedParams

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    ParameterAlternatives,
)
from pathfinder.services.strategies.wdk_counts import count_bound_criterion

_ANY_RECORD = "record"

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
    and an open slot leaves a parameter unbound.
    """
    if resolved.open_slots or definition.allowed_primary_input_record_class_names:
        return None
    return await count_bound_criterion(
        ctx.deps.site_id, record_type, search_name, resolved.params
    )


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
    resolved: ResolvedParams,
) -> list[ParameterAlternatives]:
    """The choices inside a binding that matches no record.

    A binding that matches records, and one whose count did not arrive, offers
    nothing to report.
    """
    if result_count != 0:
        return []
    offered = [
        _offered_by(info, resolved.params[info.name])
        for info in infos
        if info.is_visible
        and info.param_kind in _VOCABULARY_KINDS
        and info.name in resolved.params
    ]
    return [entry for entry in offered if entry is not None]


async def record_and_count_criterion(
    ctx: RunContext[AgentDeps],
    criterion: Criterion,
    *,
    record_type: str,
    definition: WDKSearch,
    resolved: ResolvedParams,
    infos: Sequence[ParameterInfo],
) -> tuple[int | None, list[ParameterAlternatives]]:
    """Record the criterion, then measure the binding it holds.

    The count follows the record, so the criterion stays bound whatever the
    count says and whether or not the site answers one.
    """
    state = ctx.deps.agent_state
    state.frame_set_criterion(criterion)
    count = await bound_count(
        ctx, resolved, record_type, criterion.search_name, definition
    )
    alternatives = empty_binding_alternatives(count, infos, resolved)
    state.frame_record_alternatives(criterion.id, alternatives)
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
    counted = count_noun(result_count, record_type or _ANY_RECORD)
    line = f"{bound}, {counted}"
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
