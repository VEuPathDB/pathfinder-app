"""The parameters of a search a sweep can vary, and the grid they support."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import prod

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamKind, ParamValue, from_wire
from veupathdb_mcp.catalog import ParameterInfo, get_search_parameters

from pathfinder.services.parameter_optimization.config import (
    SWEEP_BUDGET_MIN,
    ParameterSpec,
)
from pathfinder.services.parameter_optimization.sweep import enumerate_spec_values

_VOCABULARY_KINDS = frozenset({"single-pick-vocabulary", "multi-pick-vocabulary"})
_SCALAR_NUMBER_KINDS = frozenset({"number", "string"})

# A parameter a sweep holds at one value is not a variable, so two is the
# narrowest grid a spec can carry.
_MIN_LEVELS = 2


class _StepTerms(BaseModel):
    """The vocabulary terms one value of a step names."""

    terms: list[str] = Field(default_factory=list)

    @field_validator("terms", mode="before")
    @classmethod
    def _one_or_many(cls, raw: JsonValue) -> JsonValue:
        return raw if isinstance(raw, list) else [raw]


def _held_terms(info: ParameterInfo, current_values: Mapping[str, str]) -> list[str]:
    """The terms the step already holds for this parameter."""
    if info.name not in current_values:
        return []
    decoded = from_wire(info.param_kind, current_values[info.name]).to_decoded()
    return _StepTerms.model_validate({"terms": decoded}).terms


def _depends_on_another(info: ParameterInfo) -> bool:
    """Whether the catalog ties this parameter's vocabulary to another value.

    The catalog serves a dependent vocabulary under the default parent, so a
    grid over one of these pairs terms that do not belong together.
    """
    return bool(info.vocab_depends_on or info.controls_vocab_of)


def _is_scalar_number(info: ParameterInfo) -> bool:
    if info.param_kind not in _SCALAR_NUMBER_KINDS:
        return False
    return info.param_kind != "string" or info.is_number


def _states_bounds(info: ParameterInfo) -> bool:
    return info.min is not None and info.max is not None and info.min < info.max


def _categorical_spec(
    info: ParameterInfo,
    current_values: Mapping[str, str],
) -> ParameterSpec | None:
    """The spec for a vocabulary parameter, or None when it offers one term.

    The terms the step already holds come first, so thinning the grid keeps
    the step's own setting in it.
    """
    if info.param_kind not in _VOCABULARY_KINDS:
        return None
    choices = [option.value for option in info.vocabulary()]
    if len(choices) < _MIN_LEVELS:
        return None
    held = set(_held_terms(info, current_values))
    ordered = [c for c in choices if c in held] + [c for c in choices if c not in held]
    return ParameterSpec.model_validate(
        {
            "name": info.name,
            "type": "categorical",
            "choices": ordered,
            "wdkKind": info.param_kind,
        }
    )


def _numeric_spec(info: ParameterInfo) -> ParameterSpec | None:
    """The spec for a numeric parameter whose catalog entry states its bounds."""
    if not _is_scalar_number(info) or not _states_bounds(info):
        return None
    return ParameterSpec.model_validate(
        {
            "name": info.name,
            "type": "numeric",
            "min": info.min,
            "max": info.max,
            "wdkKind": info.param_kind,
        }
    )


def _spec_for(
    info: ParameterInfo,
    current_values: Mapping[str, str],
) -> ParameterSpec | None:
    """The sweep spec this parameter supports, or None when it supports none."""
    if not info.is_visible or _depends_on_another(info):
        return None
    return _categorical_spec(info, current_values) or _numeric_spec(info)


def tunable_parameter_specs(
    parameters: Sequence[ParameterInfo],
    current_values: Mapping[str, str] | None = None,
) -> list[ParameterSpec]:
    """Every parameter of a search a sweep can vary, in catalog order."""
    held = current_values or {}
    return [spec for spec in (_spec_for(info, held) for info in parameters) if spec]


def tunable_parameter_names(parameters: Sequence[ParameterInfo]) -> list[str]:
    """The names of those parameters."""
    return [spec.name for spec in tunable_parameter_specs(parameters)]


def _nothing_tunable(search_name: str, parameters: Sequence[ParameterInfo]) -> str:
    """Why this search publishes no parameter a sweep can vary."""
    visible = [info for info in parameters if info.is_visible]
    children = [info.name for info in visible if info.vocab_depends_on]
    parents = [
        info.name
        for info in visible
        if info.controls_vocab_of and not info.vocab_depends_on
    ]
    unbounded = [
        info.name
        for info in visible
        if not _depends_on_another(info)
        and _is_scalar_number(info)
        and not _states_bounds(info)
    ]
    reasons: list[str] = []
    if unbounded:
        reasons.append(f"WDK states no bounds for {', '.join(unbounded)}")
    if children:
        reasons.append(f"{', '.join(children)} depends on another parameter")
    if parents:
        reasons.append(f"{', '.join(parents)} decides another parameter's vocabulary")
    base = (
        f"{search_name} has no tunable parameters: a sweep varies a vocabulary "
        "parameter that stands on its own, or a numeric parameter whose bounds "
        "WDK states."
    )
    return base if not reasons else f"{base} {'; '.join(reasons)}."


def _with_levels(spec: ParameterSpec, levels: int) -> ParameterSpec:
    """The same spec over fewer values. Never widens the grid."""
    if spec.param_type == "categorical":
        return spec.model_copy(update={"choices": (spec.choices or [])[:levels]})
    low = spec.min or 0.0
    high = spec.max or 0.0
    return spec.model_copy(update={"step": (high - low) / (levels - 1)})


def _capped(specs: list[ParameterSpec], budget: int) -> list[ParameterSpec]:
    """The widest grid inside ``budget``, thinning the broadest spec first.

    A spec already at the narrowest grid cannot thin further, so the last
    parameter leaves the sweep instead.
    """
    kept = list(specs)
    while kept:
        levels = [len(enumerate_spec_values(spec)) for spec in kept]
        if prod(levels) <= budget:
            return kept
        widest = levels.index(max(levels))
        if levels[widest] <= _MIN_LEVELS:
            kept.pop()
            continue
        thinned = _with_levels(kept[widest], levels[widest] - 1)
        if len(enumerate_spec_values(thinned)) >= levels[widest]:
            kept.pop()
            continue
        kept[widest] = thinned
    return kept


def parameter_space_for_search(
    search_name: str,
    parameters: Sequence[ParameterInfo],
    *,
    names: Sequence[str] | None = None,
    budget: int,
    current_values: Mapping[str, str] | None = None,
) -> list[ParameterSpec]:
    """The sweep grid for a search, capped at ``budget`` trials.

    Raises when the budget buys no comparison, when ``names`` is empty, when
    the search offers no tunable parameter, and when ``names`` asks for one
    that is not tunable.
    """
    if budget < SWEEP_BUDGET_MIN:
        msg = (
            f"{search_name} cannot be swept on a budget of {budget}: a sweep "
            f"compares at least {SWEEP_BUDGET_MIN} settings."
        )
        raise ValueError(msg)
    if names is not None and not names:
        msg = f"{search_name} cannot be swept: the request names no parameter to vary."
        raise ValueError(msg)
    tunable = tunable_parameter_specs(parameters, current_values)
    if not tunable:
        raise ValueError(_nothing_tunable(search_name, parameters))
    if names is None:
        return _capped(tunable, budget)
    wanted = list(names)
    known = {spec.name for spec in tunable}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        msg = (
            f"{search_name} cannot sweep {', '.join(unknown)}. "
            f"Its tunable parameters are {', '.join(sorted(known))}."
        )
        raise ValueError(msg)
    return _capped([spec for spec in tunable if spec.name in set(wanted)], budget)


async def search_parameter_metadata(
    site_id: str,
    record_type: str,
    search_name: str,
) -> list[ParameterInfo]:
    """The catalog's own parameter entries for one search."""
    resolved = await get_search_parameters(
        SearchContext(site_id, record_type, search_name)
    )
    return list(resolved.parameters)


class SweepPlan(CamelModel):
    """The grid one sweep varies and the values it holds fixed."""

    model_config = ConfigDict(frozen=True)

    parameter_space: list[ParameterSpec] = Field(default_factory=list)
    fixed_parameters: dict[str, ParamValue] = Field(default_factory=dict)


def sweep_plan(
    search_name: str,
    parameters: Sequence[ParameterInfo],
    step_values: Mapping[str, str],
    *,
    names: Sequence[str] | None = None,
    budget: int,
) -> SweepPlan:
    """The grid for a built step, around the values that step already holds."""
    space = parameter_space_for_search(
        search_name,
        parameters,
        names=names,
        budget=budget,
        current_values=step_values,
    )
    kinds: dict[str, ParamKind] = {info.name: info.param_kind for info in parameters}
    return SweepPlan(
        parameter_space=space,
        fixed_parameters={
            name: from_wire(kinds[name], wire)
            for name, wire in step_values.items()
            if name in kinds
        },
    )
