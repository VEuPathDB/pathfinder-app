from __future__ import annotations

import json
from collections.abc import Callable

from veupathdb.domain.strategy import (
    ColocationParams,
    StepFilter,
    StepSettings,
    settings_of,
)

from strategist.domain.strategy.expression_handles import cut_stated
from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.strategy.spec_tree import node_for

__all__ = [
    "colocation_text",
    "criterion_settings",
    "settings_change_text",
    "settings_text",
]

_OWN_LINES = frozenset({"search_name", "parameters"})
_NAMED_FIRST = ("operation", "strand")
_UNSET = "(unset)"
_FILTER_VALUE_CHARS = 24
_USUAL = ColocationParams().model_dump(by_alias=True)


def colocation_text(params: ColocationParams) -> str:
    stated = params.model_dump(by_alias=True)
    rest = [
        f"{name} {value}"
        for name, value in stated.items()
        if name not in _NAMED_FIRST and value != _USUAL[name]
    ]
    return f"colocation {', '.join([*(stated[n] for n in _NAMED_FIRST), *rest])}"


def _operator(settings: StepSettings) -> str | None:
    return None if settings.operator is None else f"operator {settings.operator.value}"


def _colocation(settings: StepSettings) -> str | None:
    params = settings.colocation_params
    return None if params is None else colocation_text(params)


def _filters(settings: StepSettings) -> str | None:
    if not settings.filters:
        return None
    return f"filters {', '.join(f.name for f in settings.filters)}"


def _weight(settings: StepSettings) -> str | None:
    return None if settings.wdk_weight is None else f"weight {settings.wdk_weight}"


def _expanded_strategy(settings: StepSettings) -> str | None:
    if settings.expanded_strategy_id is None or settings.expanded_name is not None:
        return None
    return f"expands strategy {settings.expanded_strategy_id}"


def _expanded_name(settings: StepSettings) -> str | None:
    name = settings.expanded_name
    return None if name is None else f'expands "{name}"'


_TEXTS: dict[str, Callable[[StepSettings], str | None]] = {
    "operator": _operator,
    "colocation_params": _colocation,
    "filters": _filters,
    "wdk_weight": _weight,
    "expanded_strategy_id": _expanded_strategy,
    "expanded_name": _expanded_name,
}


def settings_text(settings: StepSettings) -> str:
    texts = (
        _TEXTS[name](settings)
        for name in StepSettings.model_fields
        if name not in _OWN_LINES
    )
    return ", ".join(text for text in texts if text)


def criterion_settings(criterion: Criterion) -> str:
    if not criterion.search_name:
        return ""
    return settings_text(settings_of(node_for(criterion)))


def _either(value: object) -> str:
    return _UNSET if value is None else str(value)


def _filter_value(found: StepFilter) -> str:
    return cut_stated(json.dumps(found.value), _FILTER_VALUE_CHARS)


def _filter_changes(before: StepSettings, after: StepSettings) -> str:
    was = {f.name: f for f in before.filters}
    now = {f.name: f for f in after.filters}
    parts: list[str] = []
    for name in [*was, *(n for n in now if n not in was)]:
        if name not in now:
            parts.append(f"filter {name} removed")
        elif name not in was:
            parts.append(f"filter {name} added")
        elif was[name] != now[name]:
            parts.append(
                f"filter {name} {_filter_value(was[name])} -> "
                f"{_filter_value(now[name])}"
            )
    return ", ".join(parts)


def _colocation_changes(before: StepSettings, after: StepSettings) -> str:
    was, now = before.colocation_params, after.colocation_params
    if was is None or now is None:
        shown = [_either(p if p is None else colocation_text(p)) for p in (was, now)]
        return f"{shown[0]} -> {shown[1]}"
    old, new = was.model_dump(by_alias=True), now.model_dump(by_alias=True)
    moved = [
        f"{name} {old[name]} -> {new[name]}" for name in old if old[name] != new[name]
    ]
    return f"colocation {', '.join(moved)}"


def settings_change_text(name: str, before: StepSettings, after: StepSettings) -> str:
    match name:
        case "filters":
            return _filter_changes(before, after)
        case "colocation_params":
            return _colocation_changes(before, after)
        case "operator":
            return (
                f"operator {_either(before.operator and before.operator.value)} -> "
                f"{_either(after.operator and after.operator.value)}"
            )
        case "wdk_weight":
            return f"weight {_either(before.wdk_weight)} -> {_either(after.wdk_weight)}"
        case "expanded_strategy_id":
            return (
                f"expands strategy {_either(before.expanded_strategy_id)} -> "
                f"{_either(after.expanded_strategy_id)}"
            )
        case "expanded_name":
            return (
                f"expands {_either(before.expanded_name)} -> "
                f"{_either(after.expanded_name)}"
            )
        case _:
            msg = f"{name} is rendered on a line of its own"
            raise ValueError(msg)
